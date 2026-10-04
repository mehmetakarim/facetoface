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
  ffmpeg?: boolean;
};
const native = isTauri();
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
  const [provider, setProvider] = useState("cpu");
  const [many, setMany] = useState(false);
  const [mirror, setMirror] = useState(true);
  const [camera, setCamera] = useState(0);
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
      if (e.type === "diagnostics") setDiagnostics(e);
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

  async function launch(config: Record<string, unknown>, check = false) {
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
    setError("");
    setElapsed(0);
    started.current = Date.now();
    setMessage(check ? "Kaynak fotoğraf inceleniyor…" : "Motor hazırlanıyor…");
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
        setMessage("Hedef seçildi. Hazır olduğunuzda işlemi başlatın.");
      }
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
    if (mode !== "live") {
      destination = await save({
        title: "Sonucun kaydedileceği konumu seçin",
        defaultPath:
          mode === "image"
            ? "yuz-atolyesi-sonuc.png"
            : "yuz-atolyesi-sonuc.mp4",
        filters: [
          {
            name: mode === "image" ? "PNG fotoğraf" : "MP4 video",
            extensions: [mode === "image" ? "png" : "mp4"],
          },
        ],
      });
      if (!destination) return;
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
      provider,
      many_faces: many,
      mirror,
      camera,
    });
  }
  async function stop() {
    try {
      await invoke("stop_job");
    } catch (e) {
      setError(String(e));
    }
  }
  const canStart =
    !!source && (ready || !native) && (mode === "live" || !!target) && !busy;
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
          <span className="version">Yüz Atölyesi · 0.1.0</span>
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
                    Kamera numarası
                  </label>
                  <select
                    id="camera"
                    disabled={busy}
                    value={camera}
                    onChange={(e) => setCamera(Number(e.target.value))}
                  >
                    {[0, 1, 2, 3].map((n) => (
                      <option value={n} key={n}>
                        Kamera {n}
                        {n === 0 ? " · Varsayılan" : ""}
                      </option>
                    ))}
                  </select>
                  <p className="small-note">
                    Görüntü gelmezse başka bir numara deneyin. Kamera erişimi
                    yalnızca başlattığınızda istenir.
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
                    <option value="coreml">Apple hızlandırması · CoreML</option>
                  </select>
                  <p className="small-note">
                    Standart yöntem daha öngörülebilir çalışır. Apple
                    hızlandırmasının ilk hazırlığı uzun sürebilir.
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
                      Video araçları: {diagnostics.ffmpeg ? "hazır" : "eksik"}
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
