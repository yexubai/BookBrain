#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};

/// Manages the Python backend sidecar process.
struct BackendProcess {
    child: Mutex<Option<Child>>,
}

impl BackendProcess {
    fn new() -> Self {
        Self {
            child: Mutex::new(None),
        }
    }

    /// Attempt to start the Python backend server.
    /// Returns true if started successfully, false if already running or failed.
    fn start(&self, server_dir: &str) -> bool {
        let mut guard = self.child.lock().unwrap();

        // Check if already running
        if let Some(ref mut child) = *guard {
            match child.try_wait() {
                Ok(None) => return true, // Still running
                _ => {} // Exited, we'll restart
            }
        }

        println!("[BookBrain] Starting Python backend from: {}", server_dir);

        // Try python, then python3
        let result = Command::new("python")
            .args(["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"])
            .current_dir(server_dir)
            .spawn()
            .or_else(|_| {
                Command::new("python3")
                    .args(["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"])
                    .current_dir(server_dir)
                    .spawn()
            });

        match result {
            Ok(child) => {
                println!("[BookBrain] Backend started (PID: {})", child.id());
                *guard = Some(child);
                true
            }
            Err(e) => {
                eprintln!("[BookBrain] Failed to start backend: {}", e);
                false
            }
        }
    }

    /// Stop the backend process.
    fn stop(&self) {
        let mut guard = self.child.lock().unwrap();
        if let Some(ref mut child) = *guard {
            println!("[BookBrain] Stopping backend (PID: {})", child.id());
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

#[tauri::command]
fn start_backend(state: tauri::State<'_, BackendProcess>, server_path: String) -> bool {
    state.start(&server_path)
}

#[tauri::command]
fn stop_backend(state: tauri::State<'_, BackendProcess>) {
    state.stop()
}

fn main() {
    let backend = BackendProcess::new();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(backend)
        .invoke_handler(tauri::generate_handler![start_backend, stop_backend])
        .build(tauri::generate_context!())
        .expect("error while building BookBrain");

    // Resolve the server directory (relative to the exe)
    let resource_dir = app
        .path()
        .resource_dir()
        .unwrap_or_default();
    let server_dir = resource_dir.join("server");

    // Also try the development path (project root)
    let dev_server_dir = std::env::current_dir()
        .unwrap_or_default()
        .parent()
        .map(|p| p.join("server"))
        .unwrap_or_default();

    let actual_server_dir = if server_dir.join("main.py").exists() {
        server_dir
    } else if dev_server_dir.join("main.py").exists() {
        dev_server_dir
    } else {
        // Fallback: try absolute path from project structure
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_default();

        // Walk up to find server/main.py
        let mut search = exe_dir.as_path();
        loop {
            let candidate = search.join("server").join("main.py");
            if candidate.exists() {
                break search.join("server");
            }
            match search.parent() {
                Some(parent) => search = parent,
                None => break std::path::PathBuf::from("../server"),
            }
        }
    };

    // Auto-start backend if server directory exists
    {
        let backend_state = app.state::<BackendProcess>();
        if actual_server_dir.join("main.py").exists() {
            println!("[BookBrain] Found server at: {:?}", actual_server_dir);
            backend_state.start(actual_server_dir.to_str().unwrap_or("../server"));
        } else {
            println!("[BookBrain] Server directory not found, running in remote-backend mode");
            println!("[BookBrain] Searched: {:?}", actual_server_dir);
        }
    }

    app.run(|app_handle, event| {
        if let RunEvent::ExitRequested { .. } = event {
            let backend_state = app_handle.state::<BackendProcess>();
            backend_state.stop();
        }
    });
}
