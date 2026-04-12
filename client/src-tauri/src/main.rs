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
    fn start(&self, server_dir: &str, data_dir: Option<&str>) -> bool {
        let mut guard = self.child.lock().unwrap();

        // Check if already running
        if let Some(ref mut child) = *guard {
            match child.try_wait() {
                Ok(None) => return true, // Still running
                _ => {}                  // Exited, we'll restart
            }
        }

        println!("[BookBrain] Starting Python backend from: {}", server_dir);

        let args = ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"];

        // Build command with optional BOOKBRAIN_DATA_DIR env override
        let make_cmd = |exe: &str| -> Command {
            let mut cmd = Command::new(exe);
            cmd.args(args).current_dir(server_dir);
            // Forward the data directory so the server stores data in a writable location
            // (important for packaged Tauri apps where the resource dir may be read-only)
            if let Some(dir) = data_dir {
                cmd.env("BOOKBRAIN_DATA_DIR", dir)
                   .env("BOOKBRAIN_DATABASE_URL",
                        format!("sqlite+aiosqlite:///{}/bookbrain.db", dir))
                   .env("BOOKBRAIN_COVERS_DIR",
                        format!("{}/covers", dir))
                   .env("BOOKBRAIN_INDEX_DIR",
                        format!("{}/index", dir));
            }
            cmd
        };

        // Prefer the virtual environment bundled with the server directory,
        // then fall back to system Python interpreters.
        let venv_python = {
            let base = std::path::Path::new(server_dir);
            #[cfg(target_os = "windows")]
            { base.join(".venv").join("Scripts").join("python.exe") }
            #[cfg(not(target_os = "windows"))]
            { base.join(".venv").join("bin").join("python") }
        };

        let result = if venv_python.exists() {
            println!("[BookBrain] Using venv Python: {:?}", venv_python);
            make_cmd(venv_python.to_str().unwrap_or("python")).spawn()
        } else {
            // Try python → python3 → py (Windows Python Launcher)
            make_cmd("python").spawn()
                .or_else(|_| make_cmd("python3").spawn())
                .or_else(|_| make_cmd("py").spawn())
        };

        match result {
            Ok(child) => {
                println!("[BookBrain] Backend started (PID: {})", child.id());
                *guard = Some(child);
                true
            }
            Err(e) => {
                eprintln!(
                    "[BookBrain] Failed to start backend: {}. \
                    Make sure Python 3 is installed and available in PATH \
                    (try: python --version  /  python3 --version  /  py --version)",
                    e
                );
                false
            }
        }
    }

    /// Stop the backend process.
    fn stop(&self) {
        let mut guard = self.child.lock().unwrap();
        if let Some(ref mut child) = *guard {
            println!("[BookBrain] Stopping backend (PID: {})", child.id());
            kill_child(child);
        }
        *guard = None;
    }
}

/// Platform-aware process termination.
///
/// On Windows, `Child::kill()` sends `TerminateProcess` but may leave
/// orphaned child processes alive.  We use `taskkill /F /T` to force-kill
/// the entire process tree.
///
/// On Unix, a plain SIGKILL followed by `wait()` is sufficient.
fn kill_child(child: &mut Child) {
    #[cfg(target_os = "windows")]
    {
        let pid = child.id();
        // /F = force, /T = include child processes of the target
        let status = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/F", "/T"])
            .output();
        match status {
            Ok(out) if out.status.success() => {
                println!("[BookBrain] taskkill succeeded for PID {}", pid);
            }
            Ok(out) => {
                eprintln!(
                    "[BookBrain] taskkill exited with non-zero status for PID {}: {:?}",
                    pid,
                    String::from_utf8_lossy(&out.stderr)
                );
                // Fall back to Rust's built-in kill
                let _ = child.kill();
            }
            Err(e) => {
                eprintln!("[BookBrain] taskkill unavailable ({}), falling back to kill()", e);
                let _ = child.kill();
            }
        }
        // Always wait to reap the process entry
        let _ = child.wait();
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

#[tauri::command]
fn start_backend(
    state: tauri::State<'_, BackendProcess>,
    server_path: String,
    data_path: Option<String>,
) -> bool {
    state.start(&server_path, data_path.as_deref())
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

    // ── Resolve the server directory ────────────────────────────────────────
    // Priority:
    //   1. Dev path: sibling of the current working directory (client/ → server/)
    //      — preferred during development because the resource copy may contain
    //        a broken .venv (copied symlinks / hardcoded paths don't survive)
    //   2. Tauri resource_dir (used in packaged/production builds)
    //   3. Walk up from the executable until we find server/main.py
    let dev_server_dir = std::env::current_dir()
        .unwrap_or_default()
        .parent()
        .map(|p| p.join("server"))
        .unwrap_or_default();

    let resource_dir = app.path().resource_dir().unwrap_or_default();
    let server_dir = resource_dir.join("server");

    let actual_server_dir = if dev_server_dir.join("main.py").exists() {
        dev_server_dir
    } else if server_dir.join("main.py").exists() {
        server_dir
    } else {
        // Walk up from the executable to find server/main.py
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_default();

        let mut found = std::path::PathBuf::from("../server"); // last-resort fallback
        let mut search: &std::path::Path = exe_dir.as_path();
        loop {
            let candidate = search.join("server").join("main.py");
            if candidate.exists() {
                found = search.join("server");
                break;
            }
            match search.parent() {
                Some(parent) => search = parent,
                None => break,
            }
        }
        found
    };

    // ── Resolve a writable data directory ───────────────────────────────────
    // In packaged apps the resource dir is often read-only (e.g. inside
    // /Applications on macOS).  We use the OS-standard app-data location so
    // the database, covers, and FAISS index are always in a writable place.
    let data_dir: Option<String> = app
        .path()
        .app_data_dir()
        .ok()
        .map(|d| {
            // Ensure the directory exists before passing it to the server
            if let Err(e) = std::fs::create_dir_all(&d) {
                eprintln!("[BookBrain] Warning: could not create app-data dir {:?}: {}", d, e);
            }
            d.to_string_lossy().into_owned()
        });

    // ── Auto-start backend ───────────────────────────────────────────────────
    {
        let backend_state = app.state::<BackendProcess>();
        if actual_server_dir.join("main.py").exists() {
            println!("[BookBrain] Found server at: {:?}", actual_server_dir);
            backend_state.start(
                actual_server_dir.to_str().unwrap_or("../server"),
                data_dir.as_deref(),
            );
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
