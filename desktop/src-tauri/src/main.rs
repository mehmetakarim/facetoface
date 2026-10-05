#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::{json, Value};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{Emitter, Manager, State};

struct Job {
    id: String,
    child: Child,
    last: Instant,
    deadline: Duration,
    dir: PathBuf,
    terminal: bool,
    reader_done: bool,
}
#[derive(Default)]
struct Engine {
    job: Arc<Mutex<Option<Job>>>,
}
fn root() -> PathBuf {
    if let Some(path) = std::env::var_os("DLC_PROJECT_ROOT") {
        return PathBuf::from(path);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            if dir.join("engine-worker").is_dir() {
                return dir.to_path_buf();
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from("."))
}
fn runtime(root: &std::path::Path) -> (PathBuf, bool) {
    let packaged = root.join("engine-worker").join(if cfg!(windows) {
        "engine-worker.exe"
    } else {
        "engine-worker"
    });
    if packaged.is_file() {
        return (packaged, true);
    }
    (
        root.join(if cfg!(windows) {
            "venv/Scripts/python.exe"
        } else {
            "venv/bin/python"
        }),
        false,
    )
}
fn terminate(job: &mut Job) {
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/PID", &job.child.id().to_string(), "/T", "/F"])
            .creation_flags(0x08000000)
            .status();
    }

    #[cfg(unix)]
    unsafe {
        libc::kill(-(job.child.id() as i32), libc::SIGKILL);
    }
    let _ = job.child.kill();
    let _ = job.child.wait();
}
fn send(app: &tauri::AppHandle, id: &str, mut event: Value) {
    event["job_id"] = json!(id);
    let _ = app.emit("engine-event", event);
}
#[tauri::command]
fn environment() -> Value {
    let root = root();
    json!({"python":runtime(&root).0.exists(),"swap_model":root.join("models/inswapper_128.onnx").exists(),"root":root,"version":"0.1.0"})
}
/// PowerShell's -EncodedCommand takes UTF-16LE Base64: no quoting, whatever the path.
#[cfg(windows)]
fn encoded(script: &str) -> String {
    let bytes: Vec<u8> = script.encode_utf16().flat_map(u16::to_le_bytes).collect();
    STANDARD.encode(bytes)
}
#[cfg(windows)]
fn run_vcam_setup(script: PathBuf, action: &str) -> Result<(), String> {
    let inner = format!(
        "& '{}' -Action {}; exit $LASTEXITCODE",
        script.to_string_lossy().replace('\'', "''"),
        action
    );
    // Start-Process -Verb RunAs shows the UAC prompt; declining it throws (1223).
    let outer = format!(
        "try {{ $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden \
         -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand','{}'; exit $p.ExitCode }} \
         catch {{ exit 1223 }}",
        encoded(&inner)
    );
    let status = Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand"])
        .arg(encoded(&outer))
        .creation_flags(0x08000000)
        .status()
        .map_err(|_| "Kurulum başlatılamadı.")?;
    match status.code() {
        Some(0) => Ok(()),
        Some(1223) => Err("Yönetici izni verilmediği için işlem yapılmadı.".into()),
        Some(3) => Err("Sanal kamera dosyaları uygulama klasöründe bulunamadı.".into()),
        Some(4) => Err("Sanal kamera Windows'a kaydedilemedi.".into()),
        code => Err(format!("Sanal kamera işlemi tamamlanamadı ({}).", code.unwrap_or(-1))),
    }
}
/// Installs or removes the Windows 11 virtual camera (needs administrator approval).
#[tauri::command]
async fn vcam_setup(action: String) -> Result<(), String> {
    if action != "install" && action != "uninstall" {
        return Err("Geçersiz işlem.".into());
    }
    #[cfg(windows)]
    {
        let root = root();
        let script = [root.join("vcam/setup.ps1"), root.join("native/vcam/setup.ps1")]
            .into_iter()
            .find(|p| p.is_file())
            .ok_or("Sanal kamera kurulum dosyası bulunamadı.")?;
        tauri::async_runtime::spawn_blocking(move || run_vcam_setup(script, &action))
            .await
            .map_err(|_| "Kurulum yarıda kaldı.")?
    }
    #[cfg(not(windows))]
    Err("Yüz Atölyesi Kamera yalnızca Windows 11'de kullanılabilir.".into())
}
#[tauri::command]
async fn image_data(path: String) -> Result<String, String> {
    let path = PathBuf::from(path);
    let mime = match path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase()
        .as_str()
    {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "bmp" => "image/bmp",
        _ => return Err("Önizleme için PNG, JPEG, WebP veya BMP seçin.".into()),
    };
    if fs::metadata(&path).map_err(|_| "Dosya okunamadı.")?.len() > 25 * 1024 * 1024 {
        return Err("Önizleme için 25 MB'tan küçük bir fotoğraf seçin.".into());
    }
    Ok(format!(
        "data:{};base64,{}",
        mime,
        STANDARD.encode(fs::read(path).map_err(|_| "Fotoğraf okunamadı.")?)
    ))
}
#[tauri::command]
async fn start_job(
    app: tauri::AppHandle,
    engine: State<'_, Engine>,
    config: Value,
    job_id: String,
) -> Result<(), String> {
    if job_id.is_empty()
        || job_id.len() > 80
        || !job_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-')
    {
        return Err("Geçersiz işlem kimliği.".into());
    }
    let mut guard = engine
        .job
        .lock()
        .map_err(|_| "Motor durumuna erişilemedi.")?;
    if guard.is_some() {
        return Err("Önce devam eden işlemi durdurun.".into());
    }
    let root = root();
    let (python, packaged) = runtime(&root);
    if !python.exists() {
        return Err("Python ortamı bulunamadı. Proje kurulumu tamamlanmalıdır.".into());
    }
    let base = config
        .get("output")
        .and_then(Value::as_str)
        .and_then(|p| std::path::Path::new(p).parent())
        .filter(|p| p.is_dir())
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let dir = base.join(format!(".yuz-atolyesi-{}", job_id));
    fs::create_dir(&dir).map_err(|_| "Geçici çalışma klasörü oluşturulamadı.")?;
    let cache = std::env::temp_dir().join("yuz-atolyesi-cache");
    let mut command = Command::new(python);
    if !packaged {
        command.arg("-u").arg(root.join("engine/worker.py"));
    }
    let mut paths = vec![root.join("bin")];
    #[cfg(unix)]
    paths.extend([
        PathBuf::from("/opt/homebrew/bin"),
        PathBuf::from("/usr/local/bin"),
    ]);
    paths.extend(std::env::split_paths(
        &std::env::var_os("PATH").unwrap_or_default(),
    ));
    command
        .env("DLC_PROJECT_ROOT", &root)
        .current_dir(&root)
        .env("NO_ALBUMENTATIONS_UPDATE", "1")
        .env("MPLCONFIGDIR", cache.join("matplotlib"))
        .env("XDG_CACHE_HOME", &cache)
        .env("DLC_JOB_DIR", &dir)
        .env(
            "PATH",
            std::env::join_paths(paths).map_err(|_| "Çalıştırma yolu oluşturulamadı.")?,
        )
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    command.process_group(0);
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let mut child = command
        .spawn()
        .map_err(|e| format!("Motor başlatılamadı: {}", e))?;
    let stdout = child.stdout.take().ok_or("Motor iletişimi kurulamadı.")?;
    let stderr = child.stderr.take().ok_or("Motor günlüğü açılamadı.")?;
    let written = child
        .stdin
        .take()
        .ok_or("Motor girdisi açılamadı.")?
        .write_all(format!("{}\n", config).as_bytes());
    if written.is_err() {
        let _ = child.kill();
        let _ = child.wait();
        return Err("İşlem motora iletilemedi.".into());
    }
    *guard = Some(Job {
        id: job_id.clone(),
        child,
        last: Instant::now(),
        deadline: Duration::from_secs(120),
        dir,
        terminal: false,
        reader_done: false,
    });
    drop(guard);
    let job_state = engine.job.clone();
    let event_app = app.clone();
    let event_id = job_id.clone();
    thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if let Ok(event) = serde_json::from_str::<Value>(&line) {
                let mut state = job_state.lock().unwrap();
                let Some(job) = state.as_mut().filter(|j| j.id == event_id) else {
                    break;
                };
                job.last = Instant::now();
                job.deadline = Duration::from_secs(if event["type"] == "frame" { 45 } else { 150 });
                if event["type"] == "error" || event["type"] == "finished" {
                    job.terminal = true;
                }
                send(&event_app, &event_id, event);
            }
        }
        if let Ok(mut state) = job_state.lock() {
            if let Some(job) = state.as_mut().filter(|j| j.id == event_id) {
                job.reader_done = true;
            }
        }
    });
    // Keep a bounded native-library log outside the public UI.
    let log_id = job_id.clone();
    thread::spawn(move || {
        let log = std::env::temp_dir().join(format!("yuz-atolyesi-{}.log", log_id));
        if let Ok(mut file) = fs::File::create(log) {
            let mut bytes = 0;
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                if bytes < 256 * 1024 {
                    let _ = writeln!(file, "{}", line);
                    bytes += line.len();
                }
            }
        }
    });
    let monitor = engine.job.clone();
    thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(200));
        let mut state = monitor.lock().unwrap();
        let Some(job) = state.as_mut().filter(|j| j.id == job_id) else {
            return;
        };
        match job.child.try_wait() {
            Ok(Some(status)) => {
                // A process may exit before its final JSON lines are drained.
                // Keep the job alive until the reader delivers completion/error.
                if !job.reader_done && job.last.elapsed() < Duration::from_secs(5) {
                    continue;
                }
                if !job.terminal {
                    send(
                        &app,
                        &job_id,
                        json!({"type":"error","message":if status.success() {"İşlem beklenmedik biçimde sona erdi. Yeniden deneyin."} else {"Motor beklenmedik biçimde kapandı. Standart işlem seçeneğiyle yeniden deneyin."}}),
                    );
                }
                let _ = fs::remove_dir_all(&job.dir);
                *state = None;
                send(&app, &job_id, json!({"type":"exit"}));
                return;
            }
            Err(_) => {
                terminate(job);
                send(
                    &app,
                    &job_id,
                    json!({"type":"error","message":"Motorun durumu okunamadı. İşlem durduruldu."}),
                );
            }
            Ok(None) if job.last.elapsed() > job.deadline => {
                terminate(job);
                send(
                    &app,
                    &job_id,
                    json!({"type":"error","message":"Motor zamanında yanıt vermedi. İşlem güvenle durduruldu. Standart işlem seçeneğiyle yeniden deneyin."}),
                );
            }
            Ok(None) => continue,
        }
        let _ = fs::remove_dir_all(&job.dir);
        *state = None;
        send(&app, &job_id, json!({"type":"exit"}));
        return;
    });
    Ok(())
}
#[tauri::command]
async fn stop_job(app: tauri::AppHandle, engine: State<'_, Engine>) -> Result<(), String> {
    let mut state = engine
        .job
        .lock()
        .map_err(|_| "Motor durumuna erişilemedi.")?;
    if let Some(mut job) = state.take() {
        terminate(&mut job);
        let _ = fs::remove_dir_all(&job.dir);
        send(
            &app,
            &job.id,
            json!({"type":"stopped","message":"İşlem durduruldu. Yeni bir işlem başlatabilirsiniz."}),
        );
    }
    Ok(())
}
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Engine::default())
        .setup(|app| {
            use tauri::menu::{MenuBuilder, SubmenuBuilder};
            let application = SubmenuBuilder::new(app, "Yüz Atölyesi")
                .quit_with_text("Yüz Atölyesi’nden Çık")
                .build()?;
            let edit = SubmenuBuilder::new(app, "Düzen")
                .undo_with_text("Geri Al")
                .redo_with_text("Yinele")
                .separator()
                .cut_with_text("Kes")
                .copy_with_text("Kopyala")
                .paste_with_text("Yapıştır")
                .select_all_with_text("Tümünü Seç")
                .build()?;
            let window = SubmenuBuilder::new(app, "Pencere")
                .minimize_with_text("Simge Durumuna Küçült")
                .close_window_with_text("Pencereyi Kapat")
                .build()?;
            app.set_menu(
                MenuBuilder::new(app)
                    .items(&[&application, &edit, &window])
                    .build()?,
            )?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            environment,
            image_data,
            start_job,
            stop_job,
            vcam_setup
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Ok(mut state) = window.state::<Engine>().job.lock() {
                    if let Some(mut job) = state.take() {
                        terminate(&mut job);
                        let _ = fs::remove_dir_all(job.dir);
                    }
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("Yüz Atölyesi başlatılamadı")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Ok(mut state) = app.state::<Engine>().job.lock() {
                    if let Some(mut job) = state.take() {
                        terminate(&mut job);
                        let _ = fs::remove_dir_all(job.dir);
                    }
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[cfg(windows)]
    fn cancellation_stops_windows_worker() {
        let child = Command::new("cmd.exe")
            .args(["/C", "ping -n 60 127.0.0.1 >NUL"])
            .creation_flags(0x08000000)
            .spawn()
            .unwrap();
        let mut job = Job {
            id: "test".into(),
            child,
            last: Instant::now(),
            deadline: Duration::from_secs(150),
            dir: PathBuf::new(),
            terminal: false,
            reader_done: false,
        };
        let started = Instant::now();
        terminate(&mut job);
        assert!(started.elapsed() < Duration::from_secs(10));
        assert!(!job.child.try_wait().unwrap().unwrap().success());
    }

    #[test]
    #[cfg(unix)]
    fn cancellation_kills_a_nonresponsive_worker() {
        let child = Command::new("/bin/sleep")
            .arg("60")
            .process_group(0)
            .spawn()
            .unwrap();
        let mut job = Job {
            id: "test".into(),
            child,
            last: Instant::now(),
            deadline: Duration::from_secs(150),
            dir: PathBuf::new(),
            terminal: false,
            reader_done: false,
        };
        let started = Instant::now();
        terminate(&mut job);
        assert!(started.elapsed() < Duration::from_secs(3));
        assert!(!job.child.try_wait().unwrap().unwrap().success());
    }
}
