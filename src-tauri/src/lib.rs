use std::{
    path::{Path, PathBuf},
    process::Command as StdCommand,
};

use tauri::{Manager, Theme, WebviewWindow};
use tauri_plugin_shell::{
    process::CommandChild,
    process::CommandEvent,
    ShellExt,
};

fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(|path| path.to_path_buf())
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")))
}

fn attach_command_logs(mut rx: tauri::async_runtime::Receiver<CommandEvent>, process_pid: u32, label: &'static str) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let line = String::from_utf8_lossy(&line).trim().to_string();
                    if !line.is_empty() {
                        log::info!("{label}[{process_pid}] stdout: {line}");
                    }
                }
                CommandEvent::Stderr(line) => {
                    let line = String::from_utf8_lossy(&line).trim().to_string();
                    if !line.is_empty() {
                        log::error!("{label}[{process_pid}] stderr: {line}");
                    }
                }
                CommandEvent::Error(error) => {
                    log::error!("{label}[{process_pid}] erro: {error}");
                }
                CommandEvent::Terminated(payload) => {
                    log::error!(
                        "{label}[{process_pid}] encerrado: code={:?} signal={:?}",
                        payload.code,
                        payload.signal
                    );
                }
                _ => {}
            }
        }
    });
}

fn dev_python_candidates() -> Vec<PathBuf> {
    let root = workspace_root();
    let mut candidates = vec![
        root.join(".venv").join("bin").join("python3"),
        root.join(".venv").join("bin").join("python"),
        root.join(".venv").join("Scripts").join("python.exe"),
    ];

    #[cfg(target_os = "windows")]
    {
        candidates.push(PathBuf::from("python"));
        candidates.push(PathBuf::from("py"));
    }

    #[cfg(not(target_os = "windows"))]
    {
        candidates.push(PathBuf::from("python3"));
        candidates.push(PathBuf::from("python"));
    }

    candidates
}

fn spawn_dev_api(app: &tauri::AppHandle) -> Option<CommandChild> {
    let workspace = workspace_root();
    let api_script = workspace.join("api.py");
    if !api_script.exists() {
        log::error!("api.py nao encontrado em {}", api_script.display());
        return None;
    }

    #[cfg(target_family = "unix")]
    {
        let _ = StdCommand::new("sh")
            .args(["-c", "lsof -ti:8000 | xargs kill -9 2>/dev/null || true"])
            .status();
    }

    let shell = app.shell();
    let python_path = dev_python_candidates()
        .into_iter()
        .find(|candidate| candidate.is_file() || candidate.components().count() == 1);

    let Some(python_path) = python_path else {
        log::error!("Nenhum interpretador Python encontrado para rodar a API em modo dev.");
        return None;
    };

    let args: Vec<String> = if cfg!(target_os = "windows")
        && python_path
            .file_name()
            .and_then(|value| value.to_str())
            .map(|value| value.eq_ignore_ascii_case("py"))
            .unwrap_or(false)
    {
        vec![api_script.to_string_lossy().to_string()]
    } else {
        vec![api_script.to_string_lossy().to_string()]
    };

    let command = if cfg!(target_os = "windows")
        && python_path
            .file_name()
            .and_then(|value| value.to_str())
            .map(|value| value.eq_ignore_ascii_case("py"))
            .unwrap_or(false)
    {
        shell
            .command(python_path)
            .arg(api_script.to_string_lossy().to_string())
    } else {
        shell.command(python_path).args(args)
    };

    match command
        .current_dir(&workspace)
        .env("PYTHONUNBUFFERED", "1")
        .env("AUTO_LIQUID_DEV", "1")
        .spawn()
    {
        Ok((rx, child)) => {
            let pid = child.pid();
            attach_command_logs(rx, pid, "api-dev");
            log::info!(
                "API dev iniciada a partir de {} com workspace {}",
                api_script.display(),
                workspace.display()
            );
            Some(child)
        }
        Err(error) => {
            log::error!("Falha ao iniciar api.py em modo dev: {error}");
            None
        }
    }
}

fn sidecar_dir() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    exe.parent().map(|dir| dir.to_path_buf())
}

fn sidecar_paths() -> Vec<PathBuf> {
    let Some(dir) = sidecar_dir() else {
        return Vec::new();
    };

    let mut paths = Vec::new();

    if let Ok(entries) = std::fs::read_dir(&dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };

            let is_api_sidecar = name == "api"
                || name.starts_with("api-")
                || name == "api.exe"
                || name.starts_with("api-") && name.ends_with(".exe");

            if is_api_sidecar {
                paths.push(path);
            }
        }
    }

    paths.sort();
    paths.dedup();
    paths
}

#[cfg(target_family = "unix")]
fn ensure_executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;

    if let Ok(metadata) = std::fs::metadata(path) {
        let mut permissions = metadata.permissions();
        let mode = permissions.mode();
        if mode & 0o111 == 0 {
            permissions.set_mode(mode | 0o755);
            let _ = std::fs::set_permissions(path, permissions);
        }
    }
}

#[cfg(target_os = "macos")]
fn prepare_macos_sidecar() {
    let _ = StdCommand::new("sh")
        .args(["-c", "lsof -ti:8000 | xargs kill -9 2>/dev/null || true"])
        .status();

    let current_exe = std::env::current_exe().ok();
    let bundle_root = current_exe
        .as_ref()
        .and_then(|path| path.ancestors().nth(3))
        .map(|path| path.to_path_buf());

    let sidecars = sidecar_paths();

    if !sidecars.is_empty() {
        for path in &sidecars {
            ensure_executable(path);
        }

        let mut quarantine_targets = Vec::new();
        if let Some(exe) = current_exe.as_ref() {
            quarantine_targets.push(exe.as_path());
        }
        for path in &sidecars {
            quarantine_targets.push(path.as_path());
        }
        if let Some(bundle_root) = bundle_root.as_ref() {
            quarantine_targets.push(bundle_root.as_path());
        }

        for target in quarantine_targets {
            let _ = StdCommand::new("xattr")
                .args(["-dr", "com.apple.quarantine"])
                .arg(target)
                .status();
        }

        for path in &sidecars {
            log::info!("Sidecar macOS preparado em {}", path.display());
        }
    } else {
        log::warn!("Nao foi possivel localizar o sidecar para preparar o macOS.");
    }
}

#[cfg(target_os = "windows")]
fn prepare_windows_sidecar() {
    use std::os::windows::process::CommandExt;

    const CREATE_NO_WINDOW: u32 = 0x08000000;

    match StdCommand::new("taskkill")
        .args(["/F", "/T", "/IM", "api.exe"])
        .creation_flags(CREATE_NO_WINDOW)
        .status() {
        Ok(status) => {
            log::info!("Limpeza do sidecar api.exe no Windows concluida: {status}");
        }
        Err(error) => {
            log::warn!("Nao foi possivel encerrar o sidecar api.exe no Windows: {error}");
        }
    }
}

// --- Suporte a ícone com tema (dark / light) ---

fn icon_bytes_for_theme(theme: &Theme) -> &'static [u8] {
    match theme {
        Theme::Dark => include_bytes!("../icons/128x128@dark.png"),
        _           => include_bytes!("../icons/128x128.png"),
    }
}

fn apply_theme_icon(window: &WebviewWindow, theme: &Theme) {
    let png_bytes = icon_bytes_for_theme(theme);
    match image::load_from_memory(png_bytes) {
        Ok(img) => {
            // resize_exact garante que width*height == raw.len()/4 sempre
            let rgba = img
                .resize_exact(128, 128, image::imageops::FilterType::Lanczos3)
                .into_rgba8();
            let (width, height) = rgba.dimensions();
            let raw = rgba.into_raw();
            let icon = tauri::image::Image::new_owned(raw, width, height);
            if let Err(e) = window.set_icon(icon) {
                log::warn!("Falha ao trocar ícone do tema: {e}");
            }
        }
        Err(e) => log::warn!("Falha ao decodificar ícone do tema: {e}"),
    }
}

#[tauri::command]
fn set_app_theme_icon(app: tauri::AppHandle, theme: String) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "janela principal não encontrada".to_string())?;

    let normalized = theme.to_ascii_lowercase();
    let selected_theme = match normalized.as_str() {
        "dark" => Theme::Dark,
        "light" => Theme::Light,
        // Para "system" (ou valor inesperado), usa o tema atual da janela/SO.
        _ => window.theme().unwrap_or(Theme::Light),
    };

    apply_theme_icon(&window, &selected_theme);
    Ok(())
}

// -------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![set_app_theme_icon])
        .setup(|app| {
            app.handle().plugin(
                tauri_plugin_log::Builder::default()
                    .level(log::LevelFilter::Info)
                    .build(),
            )?;

            // Aplicar ícone conforme tema atual e escutar mudanças futuras
            if let Some(window) = app.get_webview_window("main") {
                let theme = window.theme().unwrap_or(Theme::Light);
                apply_theme_icon(&window, &theme);

                let win_clone = window.clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::ThemeChanged(theme) = event {
                        apply_theme_icon(&win_clone, theme);
                    }
                });
            }

            if cfg!(debug_assertions) {
                let child = spawn_dev_api(app.handle());
                if child.is_none() {
                    return Err("falha ao iniciar api.py em modo dev".into());
                }
                log::info!(
                    "API em modo dev iniciada em segundo plano. A interface sera exibida imediatamente e aguardara a conexao local."
                );
            } else {
                #[cfg(target_os = "macos")]
                {
                    prepare_macos_sidecar();
                }

                #[cfg(target_os = "windows")]
                {
                    prepare_windows_sidecar();
                }

                let shell = app.shell();
                let (rx, sidecar) = shell
                    .sidecar("api")
                    .expect("sidecar 'api' não encontrado em src-tauri/binaries/")
                    .spawn()
                    .expect("falha ao iniciar o sidecar api");
                let sidecar_pid = sidecar.pid();
                attach_command_logs(rx, sidecar_pid, "api");

                log::info!(
                    "Sidecar da API iniciado em segundo plano. A interface sera exibida imediatamente e aguardara a conexao local."
                );
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
