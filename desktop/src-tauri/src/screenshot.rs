// Roura Agent Desktop - Screenshot Capture
// © Roura.io

use base64::{engine::general_purpose::STANDARD, Engine};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Screenshot result
#[derive(Debug, Serialize, Deserialize)]
pub struct ScreenshotResult {
    /// Base64-encoded image data
    pub data: String,
    /// Image format (png, jpeg)
    pub format: String,
    /// Width in pixels
    pub width: u32,
    /// Height in pixels
    pub height: u32,
    /// File path if saved
    pub path: Option<String>,
}

/// Region for partial screenshot
#[derive(Debug, Serialize, Deserialize)]
pub struct CaptureRegion {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

/// Capture full screenshot
#[tauri::command]
pub async fn capture_screenshot(save_path: Option<String>) -> Result<ScreenshotResult, String> {
    #[cfg(target_os = "macos")]
    {
        capture_macos_screenshot(save_path, None).await
    }

    #[cfg(target_os = "windows")]
    {
        capture_windows_screenshot(save_path, None).await
    }

    #[cfg(target_os = "linux")]
    {
        capture_linux_screenshot(save_path, None).await
    }
}

/// Capture screenshot of a specific region
#[tauri::command]
pub async fn capture_region(
    region: CaptureRegion,
    save_path: Option<String>,
) -> Result<ScreenshotResult, String> {
    #[cfg(target_os = "macos")]
    {
        capture_macos_screenshot(save_path, Some(region)).await
    }

    #[cfg(target_os = "windows")]
    {
        capture_windows_screenshot(save_path, Some(region)).await
    }

    #[cfg(target_os = "linux")]
    {
        capture_linux_screenshot(save_path, Some(region)).await
    }
}

#[cfg(target_os = "macos")]
async fn capture_macos_screenshot(
    save_path: Option<String>,
    region: Option<CaptureRegion>,
) -> Result<ScreenshotResult, String> {
    use std::process::Command;

    // Create temp file path
    let temp_path = std::env::temp_dir().join(format!("roura_screenshot_{}.png", uuid::Uuid::new_v4()));

    // Build screencapture command
    let mut cmd = Command::new("screencapture");
    cmd.arg("-x"); // No sound

    if let Some(r) = &region {
        cmd.arg("-R").arg(format!("{},{},{},{}", r.x, r.y, r.width, r.height));
    }

    let final_path = if let Some(ref p) = save_path {
        PathBuf::from(p)
    } else {
        temp_path.clone()
    };

    cmd.arg(&final_path);

    let output = cmd.output()
        .map_err(|e| format!("Failed to run screencapture: {}", e))?;

    if !output.status.success() {
        return Err(format!(
            "Screenshot failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    // Read the image
    let image_data = std::fs::read(&final_path)
        .map_err(|e| format!("Failed to read screenshot: {}", e))?;

    // Get dimensions using image crate
    let img = image::load_from_memory(&image_data)
        .map_err(|e| format!("Failed to decode image: {}", e))?;

    let result = ScreenshotResult {
        data: STANDARD.encode(&image_data),
        format: "png".to_string(),
        width: img.width(),
        height: img.height(),
        path: save_path,
    };

    // Clean up temp file if not saving
    if save_path.is_none() {
        let _ = std::fs::remove_file(&temp_path);
    }

    Ok(result)
}

#[cfg(target_os = "windows")]
async fn capture_windows_screenshot(
    save_path: Option<String>,
    region: Option<CaptureRegion>,
) -> Result<ScreenshotResult, String> {
    // Windows implementation would use win32 API or powershell
    // For now, return an error suggesting external tools
    Err("Screenshot capture on Windows requires additional setup. Use Snipping Tool or Win+Shift+S.".to_string())
}

#[cfg(target_os = "linux")]
async fn capture_linux_screenshot(
    save_path: Option<String>,
    region: Option<CaptureRegion>,
) -> Result<ScreenshotResult, String> {
    use std::process::Command;

    // Try gnome-screenshot, scrot, or import (ImageMagick)
    let temp_path = std::env::temp_dir().join(format!("roura_screenshot_{}.png", uuid::Uuid::new_v4()));

    let final_path = if let Some(ref p) = save_path {
        PathBuf::from(p)
    } else {
        temp_path.clone()
    };

    // Try different screenshot tools
    let result = if let Some(r) = &region {
        // Try scrot with region
        Command::new("scrot")
            .arg("-a")
            .arg(format!("{},{},{},{}", r.x, r.y, r.width, r.height))
            .arg(&final_path)
            .output()
    } else {
        // Try gnome-screenshot first, then scrot
        let gnome_result = Command::new("gnome-screenshot")
            .arg("-f")
            .arg(&final_path)
            .output();

        if gnome_result.is_ok() && gnome_result.as_ref().unwrap().status.success() {
            gnome_result
        } else {
            Command::new("scrot")
                .arg(&final_path)
                .output()
        }
    };

    let output = result.map_err(|e| format!("Failed to run screenshot tool: {}", e))?;

    if !output.status.success() {
        return Err(format!(
            "Screenshot failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    // Read the image
    let image_data = std::fs::read(&final_path)
        .map_err(|e| format!("Failed to read screenshot: {}", e))?;

    let img = image::load_from_memory(&image_data)
        .map_err(|e| format!("Failed to decode image: {}", e))?;

    let result = ScreenshotResult {
        data: STANDARD.encode(&image_data),
        format: "png".to_string(),
        width: img.width(),
        height: img.height(),
        path: save_path,
    };

    // Clean up temp file if not saving
    if save_path.is_none() {
        let _ = std::fs::remove_file(&temp_path);
    }

    Ok(result)
}
