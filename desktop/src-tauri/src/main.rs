// Roura Agent Desktop - Tauri Application
// © Roura.io

#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

mod commands;
mod screenshot;
mod backend;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            commands::send_message,
            commands::get_config,
            commands::set_config,
            commands::list_projects,
            commands::open_project,
            commands::get_memory,
            commands::add_memory_note,
            screenshot::capture_screenshot,
            screenshot::capture_region,
            backend::start_backend,
            backend::stop_backend,
            backend::backend_status,
        ])
        .setup(|app| {
            // Initialize backend connection
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = backend::initialize(&app_handle).await {
                    eprintln!("Failed to initialize backend: {}", e);
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::DragDrop(drag_drop) = event {
                match drag_drop {
                    tauri::DragDropEvent::Drop { paths, position } => {
                        // Emit drag-drop event to frontend
                        let _ = window.emit("file-drop", serde_json::json!({
                            "paths": paths,
                            "position": { "x": position.x, "y": position.y }
                        }));
                    }
                    tauri::DragDropEvent::Enter { paths, position } => {
                        let _ = window.emit("file-drag-enter", serde_json::json!({
                            "paths": paths,
                            "position": { "x": position.x, "y": position.y }
                        }));
                    }
                    tauri::DragDropEvent::Over { position } => {
                        let _ = window.emit("file-drag-over", serde_json::json!({
                            "position": { "x": position.x, "y": position.y }
                        }));
                    }
                    tauri::DragDropEvent::Leave => {
                        let _ = window.emit("file-drag-leave", ());
                    }
                    _ => {}
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
