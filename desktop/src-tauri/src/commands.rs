// Roura Agent Desktop - Tauri Commands
// © Roura.io

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

/// Message sent to the agent
#[derive(Debug, Serialize, Deserialize)]
pub struct AgentMessage {
    pub content: String,
    pub attachments: Option<Vec<String>>,
    pub context: Option<HashMap<String, String>>,
}

/// Response from the agent
#[derive(Debug, Serialize, Deserialize)]
pub struct AgentResponse {
    pub content: String,
    pub tool_calls: Option<Vec<ToolCall>>,
    pub finished: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ToolCall {
    pub name: String,
    pub arguments: HashMap<String, serde_json::Value>,
    pub result: Option<String>,
}

/// Project information
#[derive(Debug, Serialize, Deserialize)]
pub struct Project {
    pub name: String,
    pub path: String,
    pub last_opened: Option<String>,
}

/// Memory note
#[derive(Debug, Serialize, Deserialize)]
pub struct MemoryNote {
    pub id: String,
    pub content: String,
    pub category: String,
    pub tags: Vec<String>,
    pub created_at: String,
}

/// Configuration values
#[derive(Debug, Serialize, Deserialize)]
pub struct Config {
    pub values: HashMap<String, serde_json::Value>,
}

/// Send a message to the agent
#[tauri::command]
pub async fn send_message(message: AgentMessage) -> Result<AgentResponse, String> {
    // This will communicate with the Python backend
    // For now, return a placeholder
    Ok(AgentResponse {
        content: format!("Received: {}", message.content),
        tool_calls: None,
        finished: true,
    })
}

/// Get configuration value
#[tauri::command]
pub async fn get_config(key: String) -> Result<Option<serde_json::Value>, String> {
    // Load from config file
    let config_path = dirs::config_dir()
        .ok_or("Could not find config directory")?
        .join("roura-agent")
        .join("config.json");

    if !config_path.exists() {
        return Ok(None);
    }

    let content = std::fs::read_to_string(&config_path)
        .map_err(|e| format!("Failed to read config: {}", e))?;

    let config: HashMap<String, serde_json::Value> = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse config: {}", e))?;

    Ok(config.get(&key).cloned())
}

/// Set configuration value
#[tauri::command]
pub async fn set_config(key: String, value: serde_json::Value) -> Result<(), String> {
    let config_dir = dirs::config_dir()
        .ok_or("Could not find config directory")?
        .join("roura-agent");

    std::fs::create_dir_all(&config_dir)
        .map_err(|e| format!("Failed to create config directory: {}", e))?;

    let config_path = config_dir.join("config.json");

    // Load existing config
    let mut config: HashMap<String, serde_json::Value> = if config_path.exists() {
        let content = std::fs::read_to_string(&config_path)
            .map_err(|e| format!("Failed to read config: {}", e))?;
        serde_json::from_str(&content).unwrap_or_default()
    } else {
        HashMap::new()
    };

    // Update value
    config.insert(key, value);

    // Save
    let content = serde_json::to_string_pretty(&config)
        .map_err(|e| format!("Failed to serialize config: {}", e))?;

    std::fs::write(&config_path, content)
        .map_err(|e| format!("Failed to write config: {}", e))?;

    Ok(())
}

/// List recent projects
#[tauri::command]
pub async fn list_projects() -> Result<Vec<Project>, String> {
    let config_dir = dirs::config_dir()
        .ok_or("Could not find config directory")?
        .join("roura-agent");

    let projects_path = config_dir.join("recent_projects.json");

    if !projects_path.exists() {
        return Ok(Vec::new());
    }

    let content = std::fs::read_to_string(&projects_path)
        .map_err(|e| format!("Failed to read projects: {}", e))?;

    let projects: Vec<Project> = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse projects: {}", e))?;

    Ok(projects)
}

/// Open a project
#[tauri::command]
pub async fn open_project(path: String) -> Result<Project, String> {
    let project_path = PathBuf::from(&path);

    if !project_path.exists() {
        return Err(format!("Project path does not exist: {}", path));
    }

    let name = project_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("Unknown")
        .to_string();

    let project = Project {
        name,
        path: path.clone(),
        last_opened: Some(chrono::Utc::now().to_rfc3339()),
    };

    // Update recent projects
    let config_dir = dirs::config_dir()
        .ok_or("Could not find config directory")?
        .join("roura-agent");

    std::fs::create_dir_all(&config_dir)
        .map_err(|e| format!("Failed to create config directory: {}", e))?;

    let projects_path = config_dir.join("recent_projects.json");

    let mut projects: Vec<Project> = if projects_path.exists() {
        let content = std::fs::read_to_string(&projects_path).unwrap_or_default();
        serde_json::from_str(&content).unwrap_or_default()
    } else {
        Vec::new()
    };

    // Remove existing entry for same path
    projects.retain(|p| p.path != path);

    // Add to front
    projects.insert(0, project.clone());

    // Keep only last 10
    projects.truncate(10);

    // Save
    let content = serde_json::to_string_pretty(&projects)
        .map_err(|e| format!("Failed to serialize projects: {}", e))?;

    std::fs::write(&projects_path, content)
        .map_err(|e| format!("Failed to write projects: {}", e))?;

    Ok(project)
}

/// Get memory for current project
#[tauri::command]
pub async fn get_memory(project_path: String) -> Result<Vec<MemoryNote>, String> {
    let memory_path = PathBuf::from(&project_path)
        .join(".roura")
        .join("memory.json");

    if !memory_path.exists() {
        return Ok(Vec::new());
    }

    let content = std::fs::read_to_string(&memory_path)
        .map_err(|e| format!("Failed to read memory: {}", e))?;

    let data: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse memory: {}", e))?;

    let notes = data
        .get("notes")
        .and_then(|n| n.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|n| {
                    Some(MemoryNote {
                        id: n.get("entry_id").and_then(|v| v.as_str())?.to_string(),
                        content: n.get("content").and_then(|v| v.as_str())?.to_string(),
                        category: n
                            .get("category")
                            .and_then(|v| v.as_str())
                            .unwrap_or("note")
                            .to_string(),
                        tags: n
                            .get("tags")
                            .and_then(|v| v.as_array())
                            .map(|arr| {
                                arr.iter()
                                    .filter_map(|t| t.as_str().map(|s| s.to_string()))
                                    .collect()
                            })
                            .unwrap_or_default(),
                        created_at: n
                            .get("created_at")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string(),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(notes)
}

/// Add a memory note
#[tauri::command]
pub async fn add_memory_note(
    project_path: String,
    content: String,
    category: String,
    tags: Vec<String>,
) -> Result<MemoryNote, String> {
    let memory_dir = PathBuf::from(&project_path).join(".roura");
    let memory_path = memory_dir.join("memory.json");

    std::fs::create_dir_all(&memory_dir)
        .map_err(|e| format!("Failed to create memory directory: {}", e))?;

    // Load existing memory
    let mut data: serde_json::Value = if memory_path.exists() {
        let content = std::fs::read_to_string(&memory_path).unwrap_or_default();
        serde_json::from_str(&content).unwrap_or(serde_json::json!({"notes": [], "version": 2}))
    } else {
        serde_json::json!({"notes": [], "version": 2})
    };

    // Create new note
    let note_id = uuid::Uuid::new_v4().to_string();
    let created_at = chrono::Utc::now().to_rfc3339();

    let note = serde_json::json!({
        "entry_id": note_id,
        "content": content,
        "category": category,
        "tags": tags,
        "source": "user",
        "relevance": 1.0,
        "created_at": created_at,
    });

    // Add to notes array
    if let Some(notes) = data.get_mut("notes").and_then(|n| n.as_array_mut()) {
        notes.push(note);
    }

    // Save
    let content_str = serde_json::to_string_pretty(&data)
        .map_err(|e| format!("Failed to serialize memory: {}", e))?;

    std::fs::write(&memory_path, content_str)
        .map_err(|e| format!("Failed to write memory: {}", e))?;

    Ok(MemoryNote {
        id: note_id,
        content,
        category,
        tags,
        created_at,
    })
}

// Add chrono and uuid to Cargo.toml
