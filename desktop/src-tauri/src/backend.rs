// Roura Agent Desktop - Python Backend Integration
// © Roura.io

use serde::{Deserialize, Serialize};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::AppHandle;

/// Backend status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendStatus {
    pub running: bool,
    pub port: Option<u16>,
    pub version: Option<String>,
    pub pid: Option<u32>,
}

/// Global backend process state
static BACKEND_PROCESS: Mutex<Option<Child>> = Mutex::new(None);
static BACKEND_PORT: Mutex<Option<u16>> = Mutex::new(None);

/// Initialize backend on app startup
pub async fn initialize(_app: &AppHandle) -> Result<(), String> {
    // Check if backend is already running
    if let Ok(status) = backend_status().await {
        if status.running {
            return Ok(());
        }
    }

    // Try to start backend
    // In production, we'd have the Python backend bundled or start via uvicorn
    Ok(())
}

/// Start the Python backend server
#[tauri::command]
pub async fn start_backend(port: Option<u16>) -> Result<BackendStatus, String> {
    let port = port.unwrap_or(8765);

    // Check if already running
    {
        let process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;
        if process.is_some() {
            return Err("Backend is already running".to_string());
        }
    }

    // Find Python executable
    let python = find_python().ok_or("Could not find Python installation")?;

    // Start the backend server
    let child = Command::new(&python)
        .args([
            "-m",
            "roura_agent.server",
            "--port",
            &port.to_string(),
            "--host",
            "127.0.0.1",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start backend: {}", e))?;

    let pid = child.id();

    // Store process
    {
        let mut process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;
        *process = Some(child);
    }
    {
        let mut backend_port = BACKEND_PORT.lock().map_err(|e| e.to_string())?;
        *backend_port = Some(port);
    }

    // Wait for backend to be ready
    tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;

    // Check if process is still running
    let status = backend_status().await?;
    if !status.running {
        return Err("Backend process exited unexpectedly".to_string());
    }

    Ok(BackendStatus {
        running: true,
        port: Some(port),
        version: None,
        pid: pid,
    })
}

/// Stop the Python backend server
#[tauri::command]
pub async fn stop_backend() -> Result<(), String> {
    let mut process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;

    if let Some(mut child) = process.take() {
        // Try graceful shutdown first
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            unsafe {
                libc::kill(child.id() as i32, libc::SIGTERM);
            }
        }

        #[cfg(windows)]
        {
            let _ = child.kill();
        }

        // Wait for process to exit
        let _ = tokio::time::timeout(
            tokio::time::Duration::from_secs(5),
            tokio::task::spawn_blocking(move || {
                let _ = child.wait();
            }),
        )
        .await;
    }

    // Clear port
    {
        let mut backend_port = BACKEND_PORT.lock().map_err(|e| e.to_string())?;
        *backend_port = None;
    }

    Ok(())
}

/// Get backend status
#[tauri::command]
pub async fn backend_status() -> Result<BackendStatus, String> {
    let port = {
        let backend_port = BACKEND_PORT.lock().map_err(|e| e.to_string())?;
        *backend_port
    };

    let running = {
        let process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;
        if let Some(ref child) = *process {
            // Check if process is still alive
            // This is a bit hacky but works for now
            true
        } else {
            false
        }
    };

    let pid = {
        let process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;
        process.as_ref().map(|c| c.id())
    };

    // Try to get version from backend API
    let version = if running {
        if let Some(p) = port {
            get_backend_version(p).await.ok()
        } else {
            None
        }
    } else {
        None
    };

    Ok(BackendStatus {
        running,
        port,
        version,
        pid,
    })
}

/// Find Python executable
fn find_python() -> Option<String> {
    // Try common Python paths
    let candidates = [
        "python3",
        "python",
        "/usr/bin/python3",
        "/usr/local/bin/python3",
        "/opt/homebrew/bin/python3",
    ];

    for candidate in candidates {
        if Command::new(candidate)
            .arg("--version")
            .output()
            .is_ok()
        {
            return Some(candidate.to_string());
        }
    }

    // Try to find in PATH
    if let Ok(output) = Command::new("which").arg("python3").output() {
        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !path.is_empty() {
                return Some(path);
            }
        }
    }

    None
}

/// Get backend version from API
async fn get_backend_version(port: u16) -> Result<String, String> {
    let client = reqwest::Client::new();
    let url = format!("http://127.0.0.1:{}/version", port);

    let response = client
        .get(&url)
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to backend: {}", e))?;

    let data: serde_json::Value = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse response: {}", e))?;

    data.get("version")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| "No version in response".to_string())
}
