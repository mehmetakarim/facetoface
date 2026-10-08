import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open, save } from "@tauri-apps/plugin-dialog";
import {
  ArrowRight,
  ArrowUpRight,
  Camera,
  Check,
  ChevronDown,
  CircleHelp,
  Clapperboard,
  FileImage,
  ImagePlus,
  Layers,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  ScanFace,
  Settings2,
  ShieldCheck,
  Square,
  X,
} from "lucide-react";
import "./style.css";

type Mode = "image" | "video" | "live";
type EngineEvent = {
  type: string;
  job_id: string;
  message?: string;
  image?: string;
  output?: string;
  faces?: number;
  fps?: number;
  progress?: number;
  providers?: string[];
  swap_model?: boolean;
  analysis_models?: boolean;
  occlusion_model?: boolean;
  virtual_camera?: boolean;
  cameras?: { index: number; name: string }[];
  microphones?: { id: string; name: string }[];
  native_available?: boolean;
  native_camera?: boolean;
  obs_camera?: boolean;
  mac_bridge?: boolean;
  people?: Person[];
  ffmpeg?: boolean;
};
type Person = { count: number; image: string; embedding: number[] };
const native = isTauri();
const windows = navigator.userAgent.includes("Windows");
const macos = navigator.userAgent.includes("Macintosh") || navigator.userAgent.includes("Mac OS X");
// Remembered per device; storage may be unavailable, so every access is guarded.
function stored<T extends string>(key: string, fallback: T, allowed: T[]): T {
  try {
    const value = localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}
function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Settings simply reset next time. */
  }
}
const name = (path: string) => path.split(/[\\/]/).pop() || "";
const labels = { image: "Fotoğraf", video: "Video", live: "Canlı kamera" };

function App() {
  const [mode, setMode] = useState<Mode>("image");
  const [source, setSource] = useState("");
  const [sourceImage, setSourceImage] = useState("");
  const [target, setTarget] = useState("");
  const [targetImage, setTargetImage] = useState("");
  const [result, setResult] = useState("");
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [ready, setReady] = useState(false);
  const [sourceMessage, setSourceMessage] = useState("");
  const [message, setMessage] = useState("Başlamak için bir kaynak yüz seçin.");
  const [error, setError] = useState("");
  const [fps, setFps] = useState<number>();
  const [progress, setProgress] = useState<number>();
  const [provider, setProvider] = useState(() =>
    stored(
      "provider",
      windows ? "directml" : "cpu",
      windows ? ["cpu", "directml"] : ["cpu", "coreml"],
    ),
  );
  const [many, setMany] = useState(false);
  // People found in the target; picked holds their indices.
  const [people, setPeople] = useState<Person[]>();
  const [picked, setPicked] = useState<number[]>([]);
  // Optional source photo per person index; others use the main source.
  const [personSources, setPersonSources] = useState<
    Record<number, { path: string; image: string }>
  >({});
  const [mirror, setMirror] = useState(true);
  const [occlusion, setOcclusion] = useState(
    () => stored("occlusion", "on", ["on", "off"]) === "on",
  );
  useEffect(() => remember("provider", provider), [provider]);
  useEffect(() => remember("occlusion", occlusion ? "on" : "off"), [occlusion]);
  const [camera, setCamera] = useState(0);
  const [virtualCamera, setVirtualCamera] = useState(false);
  const [record, setRecord] = useState(false);
  const [cameraSize, setCameraSize] = useState(() =>
    stored("cameraSize", "1280x720", ["640x480", "1280x720", "1920x1080"]),
  );
  useEffect(() => remember("cameraSize", cameraSize), [cameraSize]);
  const [microphones, setMicrophones] = useState<{ id: string; name: string }[]>();
  // undefined until the list arrives (then the first microphone); "" records no sound.
  const [microphone, setMicrophone] = useState<string>();
  const [vcam, setVcam] = useState<{
    native_available?: boolean;
    native_camera?: boolean;
    obs_camera?: boolean;
    mac_bridge?: boolean;
  }>();
  const [settingUp, setSettingUp] = useState(false);
  const [cameras, setCameras] = useState<{ index: number; name: string }[]>();
  const [settings, setSettings] = useState(false);
  const [help, setHelp] = useState(false);
  const [original, setOriginal] = useState(false);
  const [diagnostics, setDiagnostics] = useState<EngineEvent>();
  const [elapsed, setElapsed] = useState(0);
  const job = useRef("");
  const started = useRef(0);
  const busyRef = useRef(false);
  const subscriptionReady = useRef(false);
  const localInput = useRef<HTMLInputElement>(null);
  const localRole = useRef<"source" | "target">("source");
  const urls = useRef<string[]>([]);
  const lastFolder = useRef("");

  useEffect(() => {
    if (!native) return;
    let disposed = false;
    let off: (() => void) | undefined;
    listen<EngineEvent>("engine-event", ({ payload: e }) => {
      if (e.job_id !== job.current) return;
      if (e.message) setMessage(e.message);
      if (e.type === "source") {
        setReady(true);
        setSourceMessage(e.message || "Kaynak yüz hazır.");
      }
      if (e.type === "frame") {
        setResult(`data:image/jpeg;base64,${e.image}`);
        setOriginal(false);
        setFps(e.fps);
        setProgress(e.progress);
      }
      if (e.type === "complete") {
        setOutput(e.output || "");
        setProgress(100);
      }
      if (e.type === "diagnostics") {
        setDiagnostics(e);
        // Without a usable GPU, fall back instead of failing every job.
        if (!e.providers?.includes("DmlExecutionProvider"))
          setProvider((p) => (p === "directml" ? "cpu" : p));
      }
      if (e.type === "cameras") {
        const list = e.cameras || [];
        setCameras(list);
        const mics = e.microphones || [];
        setMicrophones(mics);
        setMicrophone((current) =>
          current === "" || mics.some((m) => m.id === current)
            ? current
            : mics[0]?.id ?? "",
        );
        setVcam({
          native_available: e.native_available,
          native_camera: e.native_camera,
          obs_camera: e.obs_camera,
          mac_bridge: e.mac_bridge,
        });
        setCamera((current) =>
          list.length && !list.some((c) => c.index === current)
            ? list[0].index
            : current,
        );
        setMessage(
          list.length
            ? `${list.length} kamera bulundu.`
            : "Kamera bulunamadı. Numarayla seçmeyi deneyin.",
        );
      }
      if (e.type === "target_faces") {
        setPeople(e.people || []);
        setPicked([]);
        setPersonSources({});
      }
      if (e.type === "error") setError(e.message || "İşlem tamamlanamadı.");
      if (["exit", "stopped"].includes(e.type)) {
        busyRef.current = false;
        setBusy(false);
        setChecking(false);
      }
    })
      .then((fn) => {
        if (disposed) fn();
        else {
          off = fn;
          subscriptionReady.current = true;
          // A reloaded page cannot track a job started by its previous
          // instance; stop it so the camera is released and new jobs can start.
          invoke("stop_job").catch(() => undefined);
        }
      })
      .catch(() =>
        setError("Motor bağlantısı kurulamadı. Uygulamayı yeniden açın."),
      );
    return () => {
      disposed = true;
      off?.();
      subscriptionReady.current = false;
    };
  }, []);
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(
      () => setElapsed(Math.floor((Date.now() - started.current) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [busy]);
  useEffect(
    () => () => {
      urls.current.forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );

  useEffect(() => {
    if (!help) return;
    const previous = document.activeElement as HTMLElement | null;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setHelp(false);
      }
      if (event.key === "Tab") {
        const buttons = Array.from(
          document.querySelectorAll<HTMLButtonElement>(".help-modal button"),
        );
        const first = buttons[0],
          last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      previous?.focus();
    };
  }, [help]);

  useEffect(() => {
    if (mode !== "live" || cameras || !native) return;
    const timer = setInterval(() => {
      if (subscriptionReady.current && !busyRef.current) {
        clearInterval(timer);
        launch({ mode: "cameras" });
      }
    }, 300);
    return () => clearInterval(timer);
  }, [mode, cameras]);
  async function launch(config: Record<string, unknown>, check = false, preserveError = false) {
    if (busyRef.current) return;
    if (!native) {
      setError(
        "Bu ekran tarayıcı önizlemesidir. Dosya işlemek için Yüz Atölyesi masaüstü uygulamasını açın.",
      );
      return;
    }
    if (!subscriptionReady.current) {
      setError(
        "Motor bağlantısı hazırlanıyor. Birkaç saniye sonra yeniden deneyin.",
      );
      return;
    }
    job.current = crypto.randomUUID();
    busyRef.current = true;
    setBusy(true);
    setChecking(check);
    if (!preserveError) setError("");
    setElapsed(0);
    started.current = Date.now();
    setMessage(
      check
        ? "Kaynak fotoğraf inceleniyor…"
        : config.mode === "cameras"
          ? "Kameralar aranıyor…"
          : "Motor hazırlanıyor…",
    );
    try {
      await invoke("start_job", { config, jobId: job.current });
    } catch (e) {
      busyRef.current = false;
      setBusy(false);
      setChecking(false);
      setError(String(e));
    }
  }
  async function choose(role: "source" | "target") {
    if (busyRef.current) return;
    if (!native) {
      localRole.current = role;
      localInput.current!.accept =
        role === "target" && mode === "video" ? "video/*" : "image/*";
      localInput.current!.click();
      return;
    }
    try {
      const video = role === "target" && mode === "video";
      const path = await open({
        multiple: false,
        title:
          role === "source"
            ? "Kaynak yüz fotoğrafını seçin"
            : video
              ? "İşlenecek videoyu seçin"
              : "İşlenecek fotoğrafı seçin",
        filters: [
          {
            name: video ? "Video" : "Fotoğraf",
            extensions: video
              ? ["mp4", "mov", "mkv", "avi", "webm"]
              : ["png", "jpg", "jpeg", "webp", "bmp"],
          },
        ],
      });
      if (!path) return;
      const image = video ? "" : await invoke<string>("image_data", { path });
      setResult("");
      setOutput("");
      setError("");
      setProgress(undefined);
      if (role === "source") {
        setSource(path);
        setSourceImage(image);
        setReady(false);
        setSourceMessage("");
        await launch({ mode: "source", source: path }, true);
      } else {
        setTarget(path);
        setTargetImage(image);
        setPeople(undefined);
        setPicked([]);
        setPersonSources({});
        await launch({ mode: "target_faces", target: path });
      }
    } catch (e) {
      setError(String(e));
    }
  }
  async function choosePersonSource(index: number) {
    if (busyRef.current || !native) return;
    try {
      const path = await open({
        multiple: false,
        title: `${index + 1}. kişi için kaynak yüz fotoğrafını seçin`,
        filters: [
          { name: "Fotoğraf", extensions: ["png", "jpg", "jpeg", "webp", "bmp"] },
        ],
      });
      if (!path) return;
      const image = await invoke<string>("image_data", { path });
      setPersonSources((current) => ({ ...current, [index]: { path, image } }));
    } catch (e) {
      setError(String(e));
    }
  }
  function localFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    urls.current.push(url);
    if (localRole.current === "source") {
      setSource(file.name);
      setSourceImage(url);
      setSourceMessage(
        "Önizleme yüklendi. Yüz doğrulaması masaüstü uygulamasında yapılır.",
      );
    } else {
      setTarget(file.name);
      setTargetImage(file.type.startsWith("image/") ? url : "");
    }
    setResult("");
    setOutput("");
    event.target.value = "";
  }
  function changeMode(next: Mode) {
    if (busy) return;
    setMode(next);
    setTarget("");
    setTargetImage("");
    setPeople(undefined);
    setPicked([]);
    setPersonSources({});
    setResult("");
    setOutput("");
    setError("");
    setFps(undefined);
    setProgress(undefined);
    setMessage(
      source
        ? "Hedefinizi seçerek devam edin."
        : "Başlamak için bir kaynak yüz seçin.",
    );
  }
  async function start() {
    if (!native) {
      setError("İşleme özelliği masaüstü uygulamasında kullanılabilir.");
      return;
    }
    if (!source || !ready || (mode !== "live" && !target)) return;
    let destination: string | null = null;
    if (mode !== "live" || record) {
      // A fresh, readable name per job so the dialog never offers an existing file.
      const now = new Date();
      const two = (n: number) => String(n).padStart(2, "0");
      const stamp =
        `${now.getFullYear()}${two(now.getMonth() + 1)}${two(now.getDate())}-` +
        `${two(now.getHours())}${two(now.getMinutes())}${two(now.getSeconds())}`;
      const base = (name(target) || "yuz-atolyesi").replace(/\.[^.]+$/, "");
      const file =
        mode === "live"
          ? `canli-kayit-${stamp}.mp4`
          : `${base}-sonuc-${stamp}.${mode === "image" ? "png" : "mp4"}`;
      destination = await save({
        title:
          mode === "live"
            ? "Canlı kaydın kaydedileceği konumu seçin"
            : "Sonucun kaydedileceği konumu seçin",
        defaultPath: lastFolder.current
          ? `${lastFolder.current}${windows ? "\\" : "/"}${file}`
          : file,
        filters: [
          {
            name: mode === "image" ? "PNG fotoğraf" : "MP4 video",
            extensions: [mode === "image" ? "png" : "mp4"],
          },
        ],
      });
      if (!destination) return;
      lastFolder.current = destination.replace(/[\\/][^\\/]*$/, "");
    }
    setResult("");
    setOutput("");
    setFps(undefined);
    setProgress(undefined);
    await launch({
      mode,
      source,
      target,
      output: destination,
      microphone: mode === "live" && record && microphone ? microphone : null,
      camera_size: cameraSize.split("x").map(Number),
      provider,
      many_faces: many,
      target_embeddings:
        !many && people ? picked.map((i) => people[i].embedding) : [],
      target_sources:
        !many && people
          ? picked.map((i) => personSources[i]?.path ?? null)
          : [],
      mirror,
      occlusion,
      virtual_camera: mode === "live" && virtualCamera,
      camera,
    });
  }
  async function setupVcam(action: "install" | "uninstall") {
    setSettingUp(true);
    setError("");
    setMessage(
      action === "install"
        ? "Yönetici izni isteniyor; Windows'un açtığı pencereyi onaylayın…"
        : "Yüz Atölyesi Kamera kaldırılıyor…",
    );
    try {
      await invoke("vcam_setup", { action });
      setMessage(
        action === "install"
          ? "Yüz Atölyesi Kamera kuruldu."
          : "Yüz Atölyesi Kamera kaldırıldı.",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setSettingUp(false);
      launch({ mode: "cameras" }, false, true);
    }
  }
  async function stop() {
    try {
      await invoke("stop_job");
    } catch (e) {
      setError(String(e));
    }
  }
  const canStart =
    !!source && (ready || !native) && (mode === "live" || !!target) && !busy && !settingUp;
  const shownImage = original ? targetImage : result || targetImage;
  return (
    <div className="shell">
      <input
        ref={localInput}
        className="hidden"
        type="file"
        onChange={localFile}
      />
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="Yüz Atölyesi ana ekranı">
          <span className="brand-mark">
            <ScanFace size={25} />
          </span>
          <span>
            yüz<span className="brand-light">atölyesi</span>
            <small>GÖRÜNTÜ ÇALIŞMA ALANI</small>
          </span>
        </a>
        <div className="nav-caption">ÇALIŞMA ALANI</div>
        <nav aria-label="İşlem türü">
          {(["image", "video", "live"] as Mode[]).map((m) => (
            <button
              key={m}
              disabled={busy}
              className={`nav-item ${mode === m ? "active" : ""}`}
              onClick={() => changeMode(m)}
            >
              {m === "image" ? (
                <FileImage size={19} />
              ) : m === "video" ? (
                <Clapperboard size={19} />
              ) : (
                <Camera size={19} />
              )}
              <span>{labels[m]}</span>
              {mode === m && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="tiny-label">KÜÇÜK BİR İPUCU</span>
          <p>
            İyi bir sonuç,
            <br />
            net bir yüzle başlar.
          </p>
          <span>
            Önden çekilmiş, iyi aydınlatılmış bir kaynak fotoğraf kullanın.
          </span>
        </div>
        <div className="sidebar-bottom">
          <button onClick={() => setHelp(true)}>
            <CircleHelp size={18} /> Nasıl kullanılır?{" "}
            <ArrowUpRight size={15} />
          </button>
          <div className="local-note">
            <ShieldCheck size={16} />
            <span>Görüntüler bu cihazda işlenir.</span>
          </div>
          <span className="version">Yüz Atölyesi · 0.2.0</span>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            Çalışma alanı <span>/</span> <strong>{labels[mode]}</strong>
          </div>
          <span className={`connection ${busy ? "working" : ""}`}>
            <i />
            {!native
              ? "Arayüz önizlemesi"
              : busy
                ? "Motor çalışıyor"
                : "Motor beklemede"}
          </span>
        </header>
        <section className="page-heading">
          <div>
            <div className="eyebrow">YÜZ ATÖLYESİ</div>
            <h1>
              {mode === "image"
                ? "Bir fotoğraf, yeni bir ifade."
                : mode === "video"
                  ? "Her karede yeni bir ifade."
                  : "Yeni ifadeniz, anında ekranda."}
            </h1>
            <p>
              {mode === "live"
                ? "Bir yüz seçin, kameranızı açın ve sonucu canlı izleyin."
                : "Kaynak yüzü seçin, hedefinizi ekleyin. Gerisini atölyeye bırakın."}
            </p>
          </div>
          <button
            className="icon-button"
            aria-label="Kullanım kılavuzunu aç"
            onClick={() => setHelp(true)}
          >
            <CircleHelp size={21} />
          </button>
        </section>
        {!native && (
          <div className="preview-notice">
            Tasarım önizlemesi{" "}
            <span>
              Dosya seçimini deneyebilirsiniz. Görüntü işleme masaüstü
              uygulamasında çalışır.
            </span>
          </div>
        )}
        <div className="workspace">
          <div className="inputs">
            <section className="card source-card">
              <div className="section-heading">
                <span className="step">01</span>
                <h2>Kaynak yüz</h2>
                <span className="required">GEREKLİ</span>
              </div>
              <p className="section-description">
                Kullanmak istediğiniz yüzün fotoğrafı.
              </p>
              <button
                className={`upload ${sourceImage ? "has-image" : ""}`}
                disabled={busy}
                onClick={() => choose("source")}
                aria-label="Kaynak yüz fotoğrafı seç"
              >
                {sourceImage ? (
                  <>
                    <img src={sourceImage} alt="Seçilen kaynak yüz fotoğrafı" />
                    <span className="replace">
                      <RefreshCw size={14} /> Fotoğrafı değiştir
                    </span>
                  </>
                ) : (
                  <>
                    <span className="upload-icon">
                      <ScanFace size={32} strokeWidth={1.3} />
                      <span>
                        <Plus size={12} />
                      </span>
                    </span>
                    <strong>Yüz fotoğrafı seçin</strong>
                    <span>Dosyalarınızdan bir fotoğraf açın</span>
                    <small>PNG, JPEG, WebP veya BMP · En fazla 25 MB</small>
                  </>
                )}
              </button>
              {source && (
                <div className="file-meta">
                  <span title={source}>{name(source)}</span>
                  {ready ? (
                    <Check size={15} />
                  ) : checking ? (
                    <LoaderCircle className="spin" size={15} />
                  ) : null}
                </div>
              )}
              <div className={`source-hint ${ready ? "valid" : ""}`}>
                {ready ? <Check size={15} /> : <ScanFace size={15} />}
                <span>
                  {sourceMessage ||
                    "Tek bir yüzün net göründüğü fotoğraflar en iyi sonucu verir."}
                </span>
              </div>
            </section>
            <section className="card target-card">
              <div className="section-heading">
                <span className="step">02</span>
                <h2>
                  {mode === "live"
                    ? "Kamera"
                    : "Hedef " + (mode === "image" ? "fotoğraf" : "video")}
                </h2>
              </div>
              <p className="section-description">
                {mode === "live"
                  ? "Görüntüsünü kullanmak istediğiniz kamera."
                  : "Yüzü değiştirmek istediğiniz " +
                    (mode === "image" ? "fotoğraf." : "video.")}
              </p>
              {mode === "live" ? (
                <>
                  <label className="select-label" htmlFor="camera">
                    Kamera
                  </label>
                  <select
                    id="camera"
                    disabled={busy}
                    value={camera}
                    onChange={(e) => {
                      setCamera(Number(e.target.value));
                      // People found with another camera do not apply.
                      setPeople(undefined);
                      setPicked([]);
                      setPersonSources({});
                    }}
                  >
                    {cameras?.length
                      ? cameras.map((c) => (
                          <option value={c.index} key={c.index}>
                            {c.name}
                          </option>
                        ))
                      : [0, 1, 2, 3].map((n) => (
                          <option value={n} key={n}>
                            Kamera {n}
                            {n === 0 ? " · Varsayılan" : ""}
                          </option>
                        ))}
                  </select>
                  <button
                    className="text-button"
                    disabled={busy || !native}
                    onClick={() => launch({ mode: "cameras" })}
                  >
                    <RefreshCw size={14} /> Kameraları yenile
                  </button>
                  <button
                    className="text-button"
                    disabled={busy || !native}
                    onClick={() => {
                      setPeople(undefined);
                      launch({ mode: "target_faces", camera });
                    }}
                  >
                    <ScanFace size={14} /> Kadrajdaki kişileri bul
                  </button>
                  <label className="select-label" htmlFor="camera-size">
                    Görüntü kalitesi
                  </label>
                  <select
                    id="camera-size"
                    value={cameraSize}
                    disabled={busy}
                    onChange={(e) => setCameraSize(e.target.value)}
                  >
                    <option value="640x480">640 × 480 · en hızlı</option>
                    <option value="1280x720">1280 × 720 · önerilen</option>
                    <option value="1920x1080">1920 × 1080 · en net, daha yavaş</option>
                  </select>
                  <label className="toggle-row">
                    <span>
                      Canlı görüntüyü kaydet
                      <small>
                        Başlatınca kayıt yeri sorulur. Durdur'a bastığınızda
                        kayıt, seçtiğiniz mikrofonun sesiyle MP4 olarak kapatılır.
                      </small>
                    </span>
                    <input
                      type="checkbox"
                      checked={record}
                      disabled={busy}
                      onChange={(e) => setRecord(e.target.checked)}
                    />
                  </label>
                  {record && (
                    <>
                      <label className="select-label" htmlFor="microphone">
                        Ses
                      </label>
                      <select
                        id="microphone"
                        value={microphone ?? ""}
                        disabled={busy}
                        onChange={(e) => setMicrophone(e.target.value)}
                      >
                        {(microphones || []).map((m) => (
                          <option value={m.id} key={m.id}>
                            {m.name}
                          </option>
                        ))}
                        <option value="">Ses kaydetme</option>
                      </select>
                    </>
                  )}
                  {(windows || macos) && (
                    <label className="toggle-row">
                      <span>
                        Sanal kameraya gönder
                        <small>
                          {macos
                            ? "Görüşme uygulamasında “OBS Virtual Camera”yı seçin. OBS’nin kamera uzantısının kurulmuş olması gerekir."
                            : vcam?.native_camera
                            ? "WhatsApp, Teams, Zoom, Meet ve diğer uygulamalarda “Yüz Atölyesi Kamera”yı seçin. Kamera, canlı görüntü başlayınca listede görünür."
                            : vcam?.native_available
                              ? "Tüm uygulamalarda görünmesi için Yüz Atölyesi Kamera'yı bir kez kurun." +
                                (vcam.obs_camera
                                  ? " Kurulana kadar “OBS Virtual Camera” kullanılır (WhatsApp'ta görünmez)."
                                  : "")
                              : vcam?.obs_camera
                                ? "Tarayıcıda (Meet vb.), Zoom, Discord veya OBS'te “OBS Virtual Camera”yı seçin. WhatsApp ve Microsoft Store uygulamalarında görünmez."
                                : "Sanal kamera için OBS Studio'yu kurun (Windows 11'de Yüz Atölyesi Kamera da kullanılabilir)."}
                        </small>
                      </span>
                      <input
                        type="checkbox"
                        checked={virtualCamera}
                        disabled={busy}
                        onChange={(e) => setVirtualCamera(e.target.checked)}
                      />
                    </label>
                  )}
                  {macos && (
                    <details className="small-note">
                      <summary>Mac’te sanal kamera nasıl kurulur?</summary>
                      <ol>
                        <li>macOS 13 veya üzerinde OBS Studio 30 ya da daha yeni bir sürümünü kurun.</li>
                        <li>OBS’de “Sanal Kamerayı Başlat” düğmesine basın. macOS isterse Sistem Ayarları’ndan OBS kamera uzantısına izin verin.</li>
                        <li>OBS’de sanal kamerayı durdurun ve OBS’yi kapatın.</li>
                        <li>Burada “Sanal kameraya gönder” seçeneğini açıp canlı görüntüyü başlatın. Görüşme uygulamasında “OBS Virtual Camera”yı seçin.</li>
                      </ol>
                      <p>İlk kurulumdan sonra OBS’nin açık kalması gerekmez. Aktarım yalnızca canlı görüntü çalışırken yapılır.</p>
                      {vcam && !vcam.mac_bridge && <p>Sanal kamera bileşeni eksik. macOS kurulum rehberindeki Python bağımlılığını yükleyin.</p>}
                    </details>
                  )}
                  {windows && vcam?.native_available && (
                    <button
                      className="text-button"
                      disabled={busy || settingUp || !native}
                      onClick={() =>
                        setupVcam(vcam.native_camera ? "uninstall" : "install")
                      }
                    >
                      {settingUp ? (
                        <LoaderCircle size={14} className="spin" />
                      ) : (
                        <Camera size={14} />
                      )}{" "}
                      {vcam.native_camera
                        ? "Yüz Atölyesi Kamera'yı kaldır"
                        : "Yüz Atölyesi Kamera'yı kur (yönetici izni ister)"}
                    </button>
                  )}
                  <p className="small-note">
                    {cameras?.length
                      ? "Yeni bir kamera taktıysanız listeyi yenileyin. Kamera erişimi yalnızca başlattığınızda istenir."
                      : "Görüntü gelmezse başka bir numara deneyin. Kamera erişimi yalnızca başlattığınızda istenir."}
                  </p>
                </>
              ) : (
                <button
                  className="target-upload"
                  onClick={() => choose("target")}
                  disabled={busy}
                >
                  {targetImage ? (
                    <img
                      src={targetImage}
                      alt="Hedef fotoğrafın küçük önizlemesi"
                    />
                  ) : (
                    <span className="target-icon">
                      {mode === "image" ? (
                        <ImagePlus size={24} />
                      ) : (
                        <Clapperboard size={24} />
                      )}
                    </span>
                  )}
                  <span>
                    <strong>
                      {target
                        ? name(target)
                        : mode === "image"
                          ? "Fotoğraf seçin"
                          : "Video seçin"}
                    </strong>
                    <small>
                      {target
                        ? "Değiştirmek için tıklayın"
                        : mode === "image"
                          ? "PNG, JPEG, WebP veya BMP"
                          : "MP4, MOV, MKV, AVI veya WebM"}
                    </small>
                  </span>
                  <Plus size={17} />
                </button>
              )}
              {people &&
                // A live scan with one person is still useful: others may join later.
                people.length > (mode === "live" ? 0 : 1) && (
                <div className="people">
                  <span className="select-label">
                    {mode === "live"
                      ? "Kadrajdaki kişiler"
                      : mode === "video"
                        ? "Videodaki kişiler"
                        : "Fotoğraftaki kişiler"}
                  </span>
                  <div className="people-grid">
                    {people.map((person, i) => (
                      <div className="person-slot" key={i}>
                      <button
                        className={`person ${picked.includes(i) ? "picked" : ""}`}
                        aria-pressed={picked.includes(i)}
                        aria-label={`Kişi ${i + 1}`}
                        disabled={busy || many}
                        onClick={() =>
                          setPicked((current) =>
                            current.includes(i)
                              ? current.filter((x) => x !== i)
                              : [...current, i],
                          )
                        }
                      >
                        <img src={`data:image/jpeg;base64,${person.image}`} alt="" />
                        {picked.includes(i) && (
                          <span className="person-check">
                            <Check size={12} />
                          </span>
                        )}
                      </button>
                      {picked.includes(i) && !many && (
                        <div className="person-source">
                          <button
                            disabled={busy || !native}
                            title={
                              personSources[i]
                                ? name(personSources[i].path)
                                : "Bu kişi için ayrı bir kaynak yüz seçin"
                            }
                            onClick={() => choosePersonSource(i)}
                          >
                            {personSources[i] ? (
                              <img src={personSources[i].image} alt="" />
                            ) : (
                              <Plus size={11} />
                            )}
                            Kaynak
                          </button>
                          {personSources[i] && (
                            <button
                              aria-label="Ana kaynağa dön"
                              title="Ana kaynağa dön"
                              disabled={busy}
                              onClick={() =>
                                setPersonSources(({ [i]: _, ...rest }) => rest)
                              }
                            >
                              <X size={11} />
                            </button>
                          )}
                        </div>
                      )}
                      </div>
                    ))}
                  </div>
                  <p className="small-note">
                    {many
                      ? "“Tüm yüzleri değiştir” açıkken herkes değiştirilir."
                      : picked.length
                        ? "Yalnızca seçtiğiniz kişiler değiştirilir; kişiler kadrajda yer değiştirse de takip edilir. Kişiye özel kaynak seçmezseniz ana kaynak yüz kullanılır."
                        : mode === "live"
                          ? "Değiştirilecek kişiyi seçin; kadraja sonradan giren diğer kişiler değiştirilmez. Seçmezseniz en soldaki yüz değiştirilir."
                          : "Değiştirilecek kişiyi seçin. Seçmezseniz her karede en soldaki yüz değiştirilir."}
                  </p>
                </div>
              )}
            </section>
            <section className="card settings-card">
              <button
                className="disclosure"
                aria-expanded={settings}
                onClick={() => setSettings(!settings)}
              >
                <Settings2 size={17} />
                <strong>Gelişmiş ayarlar</strong>
                <ChevronDown size={17} className={settings ? "rotated" : ""} />
              </button>
              {settings && (
                <div className="settings-content">
                  <label className="select-label" htmlFor="provider">
                    İşlem yöntemi
                  </label>
                  <select
                    id="provider"
                    value={provider}
                    disabled={busy}
                    onChange={(e) => setProvider(e.target.value)}
                  >
                    <option value="cpu">Standart · CPU</option>
                    {windows ? (
                      <option value="directml">
                        Ekran kartı hızlandırması · DirectML
                      </option>
                    ) : (
                      <option value="coreml">Apple hızlandırması · CoreML</option>
                    )}
                  </select>
                  <p className="small-note">
                    {windows
                      ? "Ekran kartı hızlandırması canlı kamerada ve videoda belirgin biçimde daha hızlıdır. Sorun yaşarsanız standart yöntemi seçin."
                      : "Standart yöntem daha öngörülebilir çalışır. Apple hızlandırmasının ilk hazırlığı uzun sürebilir."}
                  </p>
                  <label className="toggle-row">
                    <span>
                      Tüm yüzleri değiştir
                      <small>Kapalıyken soldaki yüz işlenir.</small>
                    </span>
                    <input
                      type="checkbox"
                      checked={many}
                      disabled={busy}
                      onChange={(e) => setMany(e.target.checked)}
                    />
                  </label>
                  <label className="toggle-row">
                    <span>
                      El ve nesneleri koru
                      <small>
                        Yüzün önündeki eli ve saç çizgisini korur. xseg.onnx
                        gerekir.
                      </small>
                    </span>
                    <input
                      type="checkbox"
                      checked={occlusion}
                      disabled={busy}
                      onChange={(e) => setOcclusion(e.target.checked)}
                    />
                  </label>
                  {mode === "live" && (
                    <label className="toggle-row">
                      <span>Görüntüyü aynala</span>
                      <input
                        type="checkbox"
                        checked={mirror}
                        disabled={busy}
                        onChange={(e) => setMirror(e.target.checked)}
                      />
                    </label>
                  )}
                  <button
                    className="text-button"
                    disabled={busy || !native}
                    onClick={() => launch({ mode: "diagnostics" })}
                  >
                    <RefreshCw size={14} /> Kurulumu kontrol et
                  </button>
                  {diagnostics && (
                    <p className="small-note">
                      Yüz değiştirme modeli:{" "}
                      {diagnostics.swap_model ? "hazır" : "eksik"}
                      <br />
                      Yüz algılama modelleri:{" "}
                      {diagnostics.analysis_models ? "hazır" : "eksik"}
                      <br />
                      El ve nesne koruması modeli:{" "}
                      {diagnostics.occlusion_model ? "hazır" : "eksik"}
                      <br />
                      Video araçları: {diagnostics.ffmpeg ? "hazır" : "eksik"}
                      {macos && (<>
                        <br />Sanal kamera aktarım bileşeni: {diagnostics.mac_bridge ? "hazır" : "eksik"}
                        <br />OBS uzantısı ve macOS izni canlı aktarım başlatılırken denetlenir.
                      </>)}
                      {windows && (
                        <>
                          <br />
                          Sanal kamera (OBS):{" "}
                          {diagnostics.virtual_camera ? "hazır" : "kurulu değil"}
                          <br />
                          Ekran kartı hızlandırması:{" "}
                          {diagnostics.providers?.includes("DmlExecutionProvider")
                            ? "hazır"
                            : "kullanılamıyor"}
                        </>
                      )}
                    </p>
                  )}
                </div>
              )}
            </section>
          </div>
          <section className="preview-panel">
            <div className="preview-header">
              <div>
                <span className="step">03</span>
                <h2>Önizleme</h2>
              </div>
              <span className="preview-tag">
                {result
                  ? "İşlenen görüntü"
                  : target
                    ? "Hedef görüntü"
                    : "SONUÇ ALANI"}
              </span>
            </div>
            <div className={`canvas ${shownImage ? "filled" : ""}`}>
              <div className="corner top-left" />
              <div className="corner top-right" />
              <div className="corner bottom-left" />
              <div className="corner bottom-right" />
              {shownImage ? (
                <img
                  className="preview-image"
                  src={shownImage}
                  alt={original ? "Özgün hedef fotoğraf" : "İşlem önizlemesi"}
                />
              ) : (
                <div className="empty-state">
                  <div className="portrait-art">
                    <div className="art-back" />
                    <div className="art-front">
                      <ScanFace size={72} strokeWidth={0.85} />
                      <span className="art-spark">✦</span>
                    </div>
                  </div>
                  <h3>
                    {mode === "live"
                      ? "Kameranız burada görünecek."
                      : target && mode === "video"
                        ? "Videonuz işlenmeye hazır."
                        : "Yeni ifadenize yer açın."}
                  </h3>
                  <p>
                    {mode === "live"
                      ? "Kaynak yüzü seçtikten sonra canlı görüntüyü başlatın."
                      : target && mode === "video"
                        ? "İşlem başladığında kareleri burada izleyebilirsiniz."
                        : "Kaynak yüzü ve hedef dosyayı seçin. Sonuç burada görünecek."}
                  </p>
                  <div className="flow-chips">
                    <span>
                      <ScanFace size={13} /> Kaynak yüz
                    </span>
                    <ArrowRight size={13} />
                    <span>
                      {mode === "live" ? (
                        <Camera size={13} />
                      ) : (
                        <FileImage size={13} />
                      )}{" "}
                      {mode === "live" ? "Kamera" : "Hedef"}
                    </span>
                    <ArrowRight size={13} />
                    <span>
                      <Layers size={13} /> Sonuç
                    </span>
                  </div>
                </div>
              )}
              {busy && (
                <div className="processing-overlay">
                  <LoaderCircle className="spin" size={17} />
                  <span>
                    {checking
                      ? "Yüz inceleniyor"
                      : result
                        ? "İşleniyor"
                        : "Hazırlanıyor"}
                  </span>
                  <span>{elapsed} sn</span>
                </div>
              )}
              {result && targetImage && (
                <div className="compare" aria-label="Görüntü karşılaştırması">
                  <button
                    className={original ? "selected" : ""}
                    onClick={() => setOriginal(true)}
                  >
                    Özgün
                  </button>
                  <button
                    className={!original ? "selected" : ""}
                    onClick={() => setOriginal(false)}
                  >
                    Sonuç
                  </button>
                </div>
              )}
            </div>
            <div className="preview-footer">
              <span>
                <span className={`status-dot ${result ? "green" : ""}`} />
                {result ? "Önizleme hazır" : "Önizleme bekleniyor"}
              </span>
              <span>
                {fps !== undefined
                  ? `${fps.toLocaleString("tr-TR")} kare/sn`
                  : "Görüntüleriniz cihazınızda kalır"}
              </span>
            </div>
          </section>
        </div>
        <div className="action-area">
          <div className="action-status" role="status" aria-live="polite">
            {error ? (
              <span className="error-text">{error}</span>
            ) : (
              <>
                <strong>
                  {output
                    ? "İşlem tamamlandı."
                    : busy
                      ? message
                      : canStart
                        ? "Her şey hazır."
                        : ready
                          ? "Kaynak yüz hazır."
                          : "Önce kaynak yüzü seçin."}
                </strong>
                <span>
                  {output
                    ? `Kaydedildi: ${output}`
                    : busy
                      ? "Bu sırada işlemi durdurabilirsiniz."
                      : canStart
                        ? mode === "live"
                          ? "Canlı görüntü yalnızca önizlenir; kaydedilmez."
                          : "Sonucun kaydedileceği konumu bir sonraki adımda seçeceksiniz."
                        : ready
                          ? "Hedefinizi seçerek devam edin."
                          : "Ardından işlemek istediğiniz görüntüyü ekleyin."}
                </span>
              </>
            )}
            {busy && progress !== undefined && (
              <progress
                value={progress}
                max={100}
                aria-label="İşlem ilerlemesi"
              />
            )}
          </div>
          {busy ? (
            <button className="primary stop" onClick={stop}>
              <Square size={16} /> İşlemi durdur
            </button>
          ) : (
            <button
              className="primary"
              disabled={!canStart}
              onClick={() => start().catch((e) => setError(String(e)))}
            >
              {mode === "live" ? <Camera size={17} /> : <Play size={17} />}{" "}
              {mode === "live" ? "Canlı görüntüyü başlat" : "İşlemi başlat"}
              <ArrowRight size={17} />
            </button>
          )}
        </div>
        <footer className="page-footer">
          <span>Yalnızca kullanma izniniz olan görüntülerle çalışın.</span>
          <button onClick={() => setHelp(true)}>
            Kısa kullanım kılavuzu <ArrowUpRight size={13} />
          </button>
        </footer>
      </main>
      {help && (
        <div className="modal-backdrop" onClick={() => setHelp(false)}>
          <section
            className="help-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="help-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="icon-button close"
              aria-label="Kılavuzu kapat"
              autoFocus
              onClick={() => setHelp(false)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">BAŞLAMAK ÇOK KOLAY</span>
            <h2 id="help-title">Üç adımda yeni bir ifade.</h2>
            <ol>
              <li>
                <strong>Kaynak yüzü seçin.</strong>
                <p>
                  Yüzün net ve önden göründüğü bir fotoğraf kullanın. Birden
                  fazla yüz varsa en büyük yüz seçilir.
                </p>
              </li>
              <li>
                <strong>Hedefi belirleyin.</strong>
                <p>
                  Fotoğraf veya video ekleyin. Canlı kullanım için soldaki
                  menüden “Canlı kamera” seçeneğine geçin.
                </p>
              </li>
              <li>
                <strong>İşlemi başlatın.</strong>
                <p>
                  Fotoğraf ve videoda önce kayıt konumunu seçin. Sonucu
                  önizleme alanında takip edin. İstediğiniz anda durdurabilirsiniz.
                </p>
              </li>
            </ol>
            <div className="help-note">
              <ShieldCheck size={20} />
              <p>
                Görüntüler bu bilgisayarda işlenir. Videoda ses varsa çıktıya eklenir. Canlı görüntü kaydedilmez; yalnızca önizleme sunulur.
              </p>
            </div>
            <p className="small-note">
              Motor yanıt vermezse işlem otomatik olarak durdurulur. Gelişmiş
              ayarlardan “Standart” yöntemini seçip yeniden deneyin. Bu sürümde
              ağız maskeleme, yüz eşleştirme ve yüz iyileştirme henüz
              bulunmuyor.
            </p>
            <button className="primary" onClick={() => setHelp(false)}>
              Anladım, başlayalım <ArrowRight size={16} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
