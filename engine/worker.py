"""One disposable worker per job. stdout is JSONL; native-library logs use stderr.

No Tk, UI globals, event loops, or imports from modules.core are used here.
The Tauri supervisor owns cancellation and kills the whole process group.
"""
import os
import sys

os.environ.setdefault('NO_ALBUMENTATIONS_UPDATE', '1')
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
if sys.platform == 'darwin':
    os.environ.setdefault('OPENCV_VIDEOIO_PRIORITY_LIST', 'AVFOUNDATION')

import base64
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

if os.environ.get('DLC_DEBUG_STACKS') == '1':
    import faulthandler
    faulthandler.dump_traceback_later(45, repeat=True, file=sys.stderr)

ROOT = Path(os.environ.get('DLC_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
SUBPROCESS_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
STARTED_AT = time.monotonic()
sys.path.insert(0, str(ROOT))
from engine.protocol import validate, encode
from engine.output import publish

# Keep an independent descriptor so C/C++ logs cannot corrupt JSON messages.
PROTOCOL = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1, encoding='utf-8', newline='\n')
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())


def emit(kind, **data):
    PROTOCOL.write(encode({'type': kind, 'elapsed_seconds': round(time.monotonic() - STARTED_AT, 2), **data}))
    PROTOCOL.flush()


def phase(message):
    emit('status', message=message)


class LatestFrameReader:
    """Reads a camera continuously and hands out only the newest frame."""

    def __init__(self, cap):
        import threading
        self.cap = cap
        self.frame = None
        self.ok = True
        self.fresh = threading.Condition()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            with self.fresh:
                self.ok, self.frame = ok, frame if ok else None
                self.fresh.notify()
            if not ok:
                return

    def read(self):
        with self.fresh:
            if self.frame is None and self.ok:
                self.fresh.wait(timeout=5)
            frame, self.frame = self.frame, None
            return frame is not None, frame

    def get(self, prop):
        return self.cap.get(prop)

    def release(self):
        self.running = False
        self.thread.join(timeout=2)
        self.cap.release()


def camera_api(cv2):
    # This OpenCV build cannot open devices through Media Foundation, and CAP_ANY
    # falls back to DirectShow anyway. Using it explicitly keeps the listed order
    # and the opened index identical.
    if sys.platform == 'darwin':
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_DSHOW if sys.platform == 'win32' else cv2.CAP_ANY


def list_cameras():
    """Device names without opening any camera, so no permission prompt appears."""
    import cv2
    cameras = []
    if sys.platform == 'win32':
        from cv2_enumerate_cameras import enumerate_cameras
        seen = {}
        for info in enumerate_cameras(camera_api(cv2)):
            # Our own output; picking it as input would feed the result back in.
            if info.name == 'OBS Virtual Camera':
                continue
            seen[info.name] = seen.get(info.name, 0) + 1
            name = info.name if seen[info.name] == 1 else f'{info.name} ({seen[info.name]})'
            cameras.append({'index': info.index, 'name': name})
    from engine.virtualcam import status
    emit('cameras', cameras=[c for c in cameras if 0 <= c['index'] <= 9], **status())


def run(config):
    if config['mode'] == 'cameras':
        list_cameras()
        return
    if config['mode'] == 'live' and config.get('virtual_camera'):
        from engine.virtualcam import installed as obs_installed, native_installed
        if not (native_installed() or obs_installed()):
            raise ValueError('Sanal kamera kurulu değil. Ayarlardan Yüz Atölyesi Kamera’yı kurun veya OBS Studio’yu yükleyin.')
    phase('Görüntü işleme bileşenleri hazırlanıyor…')
    import cv2
    import numpy as np
    import onnxruntime as ort

    model_path = ROOT / 'models' / 'inswapper_128.onnx'
    occlusion_path = ROOT / 'models' / 'xseg.onnx'
    analysis_dir = ROOT / 'models' / 'buffalo_l'
    if not analysis_dir.is_dir():
        analysis_dir = Path.home() / '.insightface' / 'models' / 'buffalo_l'
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            ffmpeg = None
    if config['mode'] == 'diagnostics':
        from engine.virtualcam import installed as virtualcam_installed, native_installed
        if config.get('check_inference'):
            from engine.inference import load_inference
            load_inference()
            if ffmpeg:
                subprocess.run([ffmpeg, '-version'], check=True, capture_output=True, timeout=15, **SUBPROCESS_FLAGS)
        emit('diagnostics', python=sys.version.split()[0], providers=ort.get_available_providers(),
             swap_model=model_path.is_file(), analysis_models=all((analysis_dir / n).is_file() for n in ['det_10g.onnx', 'w600k_r50.onnx']),
             occlusion_model=occlusion_path.is_file(), virtual_camera=virtualcam_installed(), native_camera=native_installed(), ffmpeg=bool(ffmpeg))
        return
    if not all((analysis_dir / n).is_file() for n in ['det_10g.onnx', 'w600k_r50.onnx']):
        raise ValueError('Yüz algılama modelleri eksik. det_10g.onnx ve w600k_r50.onnx dosyalarını models/buffalo_l klasörüne yerleştirin.')

    phase('Yüz analizi bileşenleri hazırlanıyor…')
    from engine.inference import load_inference
    get_model, Face = load_inference()
    phase('Fotoğraftaki yüz inceleniyor…')
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    opts.log_severity_level = 3
    # FaceAnalysis loads every model before applying allowed_modules. Loading only
    # the detector avoids allocating the unused landmark/age models at startup.
    detector = get_model(str(analysis_dir / 'det_10g.onnx'),
                                              providers=['CPUExecutionProvider'], sess_options=opts)
    # CPU is already selected above. A negative ctx_id would rebuild the session
    # and discard its thread limits in InsightFace 0.7.3.
    detector.prepare(ctx_id=0, input_size=(320, 320), det_thresh=0.5)

    def detect(frame):
        bboxes, keypoints = detector.detect(frame, max_num=0, metric='default')
        return [Face(bbox=box[:4], kps=keypoints[i], det_score=box[4])
                for i, box in enumerate(bboxes)]
    source_image = cv2.imdecode(np.fromfile(config['source'], dtype=np.uint8), cv2.IMREAD_COLOR)
    if source_image is None:
        raise ValueError('Fotoğraf okunamadı. PNG veya JPEG biçiminde başka bir dosya seçin.')
    faces = detect(source_image)
    if not faces:
        raise ValueError('Fotoğrafta yüz bulunamadı. Yüzün net ve önden göründüğü bir fotoğraf seçin.')
    source = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    emit('source', faces=len(faces), message='Kaynak yüz hazır.' if len(faces) == 1 else f'{len(faces)} yüz bulundu. En büyük yüz seçildi.')
    if config['mode'] == 'source':
        return
    phase('Kaynak yüz hazırlanıyor…')
    recognizer = get_model(str(analysis_dir / 'w600k_r50.onnx'),
                                               providers=['CPUExecutionProvider'], sess_options=opts)
    recognizer.prepare(ctx_id=0)
    recognizer.get(source_image, source)
    del recognizer
    if not model_path.is_file():
        raise ValueError('Yüz değiştirme modeli eksik. inswapper_128.onnx dosyasını models klasörüne yerleştirin.')
    provider = config.get('provider', 'cpu')
    if provider == 'coreml' and 'CoreMLExecutionProvider' not in ort.get_available_providers():
        raise ValueError('Bu bilgisayarda Apple hızlandırması kullanılamıyor. Standart işlem seçeneğini deneyin.')
    if provider == 'directml' and 'DmlExecutionProvider' not in ort.get_available_providers():
        raise ValueError('Bu bilgisayarda ekran kartı hızlandırması kullanılamıyor. Standart işlem seçeneğini deneyin.')
    phase({'cpu': 'Yüz değiştirme modeli yükleniyor…',
           'coreml': 'Apple hızlandırması hazırlanıyor. İlk açılış biraz sürebilir…',
           'directml': 'Ekran kartı hızlandırması hazırlanıyor…'}[provider])
    swap_opts = opts
    if provider == 'cpu':
        providers = ['CPUExecutionProvider']
    elif provider == 'coreml':
        providers = ['CoreMLExecutionProvider', 'CPUExecutionProvider']
    else:
        # DirectML rejects memory patterns and parallel execution. The detector stays
        # on CPU: det_10g's dynamic Reshape fails under DirectML 1.20.
        swap_opts = ort.SessionOptions()
        swap_opts.log_severity_level = 3
        swap_opts.enable_mem_pattern = False
        swap_opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # Prefer the discrete GPU on hybrid laptops instead of adapter 0.
        providers = [('DmlExecutionProvider', {'performance_preference': 'high_performance', 'device_filter': 'gpu'}),
                     'CPUExecutionProvider']
    swapper = get_model(str(model_path), providers=providers, sess_options=swap_opts)
    from engine.blend import Blender, Occluder
    occluder = None
    if config.get('occlusion', True):
        if occlusion_path.is_file():
            phase('El ve nesne koruması hazırlanıyor…')
            # XSeg is a TensorFlow export; keep it off CoreML, which is untested with it.
            occluder = Occluder(ort.InferenceSession(str(occlusion_path), swap_opts,
                                                     providers=providers if provider == 'directml' else ['CPUExecutionProvider']))
        else:
            phase('xseg.onnx bulunamadı; el ve nesne koruması olmadan devam ediliyor.')
    blender = Blender(occluder)
    phase('İşlem başlıyor…')
    last_preview = 0.0
    # Video previews are throttled to spare the encoder; live preview is the product.
    preview_interval = 1 / 30 if config['mode'] == 'live' else 0.18

    def preview(frame, **data):
        nonlocal last_preview
        now = time.monotonic()
        if now - last_preview < preview_interval and not data.get('final'):
            return
        last_preview = now
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (int(w * min(1, 900 / w)), int(h * min(1, 900 / w))))
        ok, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 78])
        if ok:
            emit('frame', image=base64.b64encode(buf).decode('ascii'), **data)

    def transform(frame):
        # Only the source needs a recognition embedding. Target faces need landmarks.
        found = detect(frame)
        selected = found if config.get('many_faces', False) else sorted(found, key=lambda f: f.bbox[0])[:1]
        for target_face in selected:
            fake, M = swapper.get(frame, target_face, source, paste_back=False)
            frame = blender.paste(frame, fake, M)
        return frame, len(selected)

    mode = config['mode']
    if mode == 'image':
        frame = cv2.imdecode(np.fromfile(config['target'], dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError('Hedef fotoğraf okunamadı.')
        frame, count = transform(frame)
        if not count:
            raise ValueError('Hedef fotoğrafta yüz bulunamadı. Başka bir fotoğraf seçin.')
        suffix = Path(config['output']).suffix
        ok, encoded = cv2.imencode(suffix, frame)
        if not ok:
            raise ValueError('Sonuç fotoğrafı oluşturulamadı.')
        publish(config['output'], data=encoded.tobytes())
        preview(frame, final=True, faces=count)
        emit('complete', output=config['output'], message='Fotoğraf kaydedildi.')
        return

    if mode == 'video' and not ffmpeg:
        raise ValueError('Video işlemek için FFmpeg kurulmalıdır.')
    cap = cv2.VideoCapture(config.get('camera', 0), camera_api(cv2)) if mode == 'live' else cv2.VideoCapture(config['target'])
    encoder = None
    temp_dir = None
    virtual_camera = None
    try:
        if not cap.isOpened():
            raise ValueError('Kamera açılamadı. Kamera numarasını ve kamera izinlerini kontrol edin.' if mode == 'live' else 'Video açılamadı. Dosya biçimini kontrol edin.')
        if mode == 'live':
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Drivers often ignore BUFFERSIZE; draining on a thread keeps processing
            # on the newest frame instead of a growing backlog.
            cap = LatestFrameReader(cap)
            phase('Kamera açık. Canlı görüntü işleniyor.')
        else:
            phase('Video işleniyor…')
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if 0 < fps <= 240 else 25.0
        total = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))) if mode == 'video' else 0
        frames = 0
        start = time.monotonic()
        while True:
            ok, frame = cap.read()
            if not ok:
                if mode == 'live':
                    raise ValueError('Kamera görüntüsü kesildi. Bağlantıyı kontrol edip yeniden başlatın.')
                break
            if mode == 'live' and config.get('mirror', True):
                frame = cv2.flip(frame, 1)
            frame, count = transform(frame)
            frames += 1
            if mode == 'live' and config.get('virtual_camera'):
                if virtual_camera is None:
                    from engine.virtualcam import open_camera
                    virtual_camera = open_camera(frame.shape[1], frame.shape[0])
                    phase(f'Sanal kamera açık. Görüntülü görüşmede "{virtual_camera.name}" kamerasını seçin.')
                # Meeting apps mirror their own self-view; others must see the true image.
                virtual_camera.send(cv2.flip(frame, 1) if config.get('mirror', True) else frame)
            if mode == 'video':
                if encoder is None:
                    # Same-volume temporary output; removed even when the process is killed by supervisor.
                    temp_dir = tempfile.TemporaryDirectory(prefix='yuz-atolyesi-', dir=os.environ.get('DLC_JOB_DIR'))
                    video_path = Path(temp_dir.name) / 'silent.mp4'
                    h, w = frame.shape[:2]
                    encoder = subprocess.Popen([ffmpeg, '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-', '-an', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', str(video_path)], stdin=subprocess.PIPE, **SUBPROCESS_FLAGS)
                encoder.stdin.write(frame.tobytes())
            preview(frame, fps=round(frames / max(0.01, time.monotonic() - start), 1), progress=min(99, round(frames / total * 100, 1)) if total else None, faces=count)
        if not frames:
            raise ValueError('Videoda okunabilir kare bulunamadı.')
        if mode == 'video':
            phase('Video kaydediliyor ve özgün ses ekleniyor…')
            encoder.stdin.close()
            if encoder.wait(timeout=90) != 0:
                raise ValueError('Video kodlanamadı. Diskte yeterli boş alan olduğundan emin olun.')
            merged_path = Path(temp_dir.name) / 'result.mp4'
            completed = subprocess.run([ffmpeg, '-v', 'error', '-n', '-i', str(video_path), '-i', config['target'], '-map', '0:v:0', '-map', '1:a:0?', '-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart', str(merged_path)], timeout=120, **SUBPROCESS_FLAGS)
            if completed.returncode:
                raise ValueError('Video kaydedilemedi. Kaynak dosyayı ve disk alanını kontrol edin.')
            publish(config['output'], source=merged_path)
            emit('complete', output=config['output'], message='Video kaydedildi.')
    finally:
        cap.release()
        if virtual_camera is not None:
            virtual_camera.close()
        if encoder is not None and encoder.poll() is None:
            encoder.kill()
            encoder.wait()
        if temp_dir:
            temp_dir.cleanup()


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.readline(1024 * 1024).decode('utf-8')
        config = validate(json.loads(raw))
        run(config)
        emit('finished')
    except Exception as error:
        import traceback
        traceback.print_exc(file=sys.stderr)
        if isinstance(error, (ValueError, FileExistsError)):
            message = str(error) if isinstance(error, ValueError) else 'Bu adda bir dosya zaten var. Farklı bir ad seçin.'
        else:
            message = 'İşlem tamamlanamadı. Motoru yeniden başlatın veya farklı bir dosya deneyin.'
        emit('error', message=message, detail=str(error))
        sys.exit(1)
