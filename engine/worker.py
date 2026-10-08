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
import traceback
from pathlib import Path

if os.environ.get('DLC_DEBUG_STACKS') == '1':
    import faulthandler
    faulthandler.dump_traceback_later(45, repeat=True, file=sys.stderr)

ROOT = Path(os.environ.get('DLC_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
SUBPROCESS_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
STARTED_AT = time.monotonic()
sys.path.insert(0, str(ROOT))
from engine.protocol import validate, encode, CAMERA_SIZES, IMAGE_EXTENSIONS, MAX_SELECTED_FACES
from engine.output import publish

# Keep an independent descriptor so C/C++ logs cannot corrupt JSON messages.
PROTOCOL = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1, encoding='utf-8', newline='\n')
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())


def emit(kind, **data):
    PROTOCOL.write(encode({'type': kind, 'elapsed_seconds': round(time.monotonic() - STARTED_AT, 2), **data}))
    PROTOCOL.flush()


def phase(message):
    emit('status', message=message)


class FakeCamera:
    """Test stand-in for a camera: replays a video file in real time, then ends."""

    def __init__(self, path):
        import cv2
        self.cap = cv2.VideoCapture(path)
        rate = self.cap.get(cv2.CAP_PROP_FPS)
        self.interval = 1 / rate if 0 < rate <= 240 else 1 / 30
        self.next = time.monotonic()

    def isOpened(self):
        return self.cap.isOpened()

    def set(self, prop, value):
        return True

    def get(self, prop):
        return self.cap.get(prop)

    def read(self):
        time.sleep(max(0.0, self.next - time.monotonic()))
        self.next += self.interval
        return self.cap.read()

    def release(self):
        self.cap.release()


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


def find_ffmpeg():
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            ffmpeg = None
    return ffmpeg


def camera_api(cv2):
    # This OpenCV build cannot open devices through Media Foundation, and CAP_ANY
    # falls back to DirectShow anyway. Using it explicitly keeps the listed order
    # and the opened index identical.
    if sys.platform == 'darwin':
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_DSHOW if sys.platform == 'win32' else cv2.CAP_ANY


def list_cameras():
    """Device names without opening any camera, so no permission prompt appears."""
    cameras = []
    if sys.platform == 'win32':
        import cv2
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
    from engine.audio import list_microphones
    emit('cameras', cameras=[c for c in cameras if 0 <= c['index'] <= 9],
         microphones=list_microphones(find_ffmpeg()), **status())


def thumbnail(frame, bbox, size=112):
    """Square JPEG of a face with some context, for the person picker."""
    import cv2
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = bbox
    side = max(x1 - x0, y1 - y0) * 1.4
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    left, top = int(max(cx - side / 2, 0)), int(max(cy - side / 2, 0))
    right, bottom = int(min(cx + side / 2, w)), int(min(cy + side / 2, h))
    crop = cv2.resize(frame[top:bottom, left:right], (size, size), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return base64.b64encode(buf).decode('ascii') if ok else ''


def sample_frames(target, samples=48):
    """The target image, or frames spread over the whole video."""
    import cv2
    import numpy as np
    if Path(target).suffix.lower() in IMAGE_EXTENSIONS:
        image = cv2.imdecode(np.fromfile(target, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Hedef fotoğraf okunamadı.')
        return [image]
    cap = cv2.VideoCapture(target)
    frames = []
    try:
        if not cap.isOpened():
            raise ValueError('Video açılamadı. Dosya biçimini kontrol edin.')
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        for position in (np.linspace(0, total - 1, min(samples, total)).astype(int) if total > 0 else []):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(position))
            ok, frame = cap.read()
            if ok:
                frames.append(frame)
        # Some containers report no frame count or cannot seek; read the start instead.
        step = 15
        for index in range(samples * step if not frames else 0):
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                frames.append(frame)
    finally:
        cap.release()
    return frames


def sample_camera(index, seconds=3.0, step=3):
    """A few seconds of the live camera; the job releases it before the live view starts."""
    import cv2
    cap = cv2.VideoCapture(index, camera_api(cv2))
    frames = []
    try:
        if not cap.isOpened():
            raise ValueError('Kamera açılamadı. Kamera seçimini ve izinlerini kontrol edin; kamerayı kullanan başka bir uygulama varsa kapatın.')
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        phase('Kadraj taranıyor; birkaç saniye kameraya bakın…')
        for _ in range(10):  # let exposure settle; first frames are often dark
            cap.read()
        until, index = time.monotonic() + seconds, 0
        while time.monotonic() < until:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                frames.append(frame)
            index += 1
    finally:
        cap.release()
    if not frames:
        raise ValueError('Kamera görüntüsü alınamadı. Kamera bağlantısını kontrol edin.')
    return frames


def find_people(frames, detect, recognizer, live=False):
    import numpy as np
    from engine.people import group
    phase('Hedefteki kişiler aranıyor…')
    faces = []
    for frame in frames:
        for face in detect(frame):
            x0, y0, x1, y1 = face.bbox
            if min(x1 - x0, y1 - y0) < 32:  # too small to recognise reliably
                continue
            recognizer.get(frame, face)
            quality = float(face.det_score) * (x1 - x0) * (y1 - y0)
            faces.append((face.normed_embedding.astype(np.float32), quality, thumbnail(frame, face.bbox)))
    people = group(faces)[:MAX_SELECTED_FACES]
    emit('target_faces',
         people=[{'count': p['count'], 'image': p['thumbnail'],
                  'embedding': [round(float(v), 5) for v in p['center']]} for p in people],
         message=(f'Kadrajda {len(people)} kişi bulundu.' if people else 'Kadrajda yüz bulunamadı.') if live
         else (f'Hedefte {len(people)} kişi bulundu.' if people else 'Hedefte yüz bulunamadı.'))


def run(config):
    if config['mode'] == 'cameras':
        list_cameras()
        return
    if sys.platform == 'win32' and config['mode'] == 'live' and config.get('virtual_camera'):
        from engine.virtualcam import installed as obs_installed, native_installed
        if not (native_installed() or obs_installed()):
            raise ValueError('Sanal kamera kurulu değil. Ayarlardan Yüz Atölyesi Kamera’yı kurun veya OBS Studio’yu yükleyin.')
    if sys.platform == 'darwin' and config['mode'] == 'live' and config.get('virtual_camera'):
        from engine.virtualcam import mac_bridge_available
        if not mac_bridge_available():
            raise ValueError('Sanal kamera bileşeni eksik. macOS kurulum rehberindeki Python bağımlılığını yükleyin.')
    phase('Görüntü işleme bileşenleri hazırlanıyor…')
    import cv2
    import numpy as np
    import onnxruntime as ort

    model_path = ROOT / 'models' / 'inswapper_128.onnx'
    occlusion_path = ROOT / 'models' / 'xseg.onnx'
    analysis_dir = ROOT / 'models' / 'buffalo_l'
    if not analysis_dir.is_dir():
        analysis_dir = Path.home() / '.insightface' / 'models' / 'buffalo_l'
    ffmpeg = find_ffmpeg()
    if config['mode'] == 'diagnostics':
        from engine.virtualcam import installed as virtualcam_installed, native_installed, mac_bridge_available
        if config.get('check_inference'):
            from engine.inference import load_inference
            load_inference()
            if ffmpeg:
                subprocess.run([ffmpeg, '-version'], check=True, capture_output=True, timeout=15, **SUBPROCESS_FLAGS)
        emit('diagnostics', python=sys.version.split()[0], providers=ort.get_available_providers(),
             swap_model=model_path.is_file(), analysis_models=all((analysis_dir / n).is_file() for n in ['det_10g.onnx', 'w600k_r50.onnx']),
             occlusion_model=occlusion_path.is_file(), virtual_camera=virtualcam_installed(), native_camera=native_installed(), mac_bridge=mac_bridge_available(), ffmpeg=bool(ffmpeg))
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

    def load_recognizer(providers=('CPUExecutionProvider',), sess_options=opts):
        model = get_model(str(analysis_dir / 'w600k_r50.onnx'), providers=list(providers), sess_options=sess_options)
        model.prepare(ctx_id=0)
        return model

    if config['mode'] == 'target_faces':
        live = not config.get('target')
        frames = sample_camera(config.get('camera', 0)) if live else sample_frames(config['target'])
        find_people(frames, detect, load_recognizer(), live)
        return
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
    recognizer = load_recognizer()
    recognizer.get(source_image, source)
    # Chosen people are recognised in every frame; otherwise the model is not needed.
    targets = None if config.get('many_faces', False) else config.get('target_embeddings') or None
    person_sources = None
    if targets:
        targets = np.asarray(targets, np.float32)
        targets /= np.linalg.norm(targets, axis=1, keepdims=True)
        # Each chosen person may have their own source photo; None means the main one.
        prepared, person_sources = {}, []
        for number, path in enumerate(config.get('target_sources') or [None] * len(targets), 1):
            if path is None:
                person_sources.append(source)
                continue
            if path not in prepared:
                image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
                candidates = detect(image) if image is not None else []
                if not candidates:
                    raise ValueError(f'{number}. kişi için seçilen fotoğrafta yüz bulunamadı. Yüzün net göründüğü bir fotoğraf seçin.')
                face = max(candidates, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                recognizer.get(image, face)
                prepared[path] = face
            person_sources.append(prepared[path])
    else:
        recognizer = None
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
    # The recognizer stays on the CPU: it runs on the analysis thread while the swap
    # runs on the GPU, and DirectML crashes the process when two threads use it at
    # once. The tracker makes recognition rare, so the CPU is fast enough.
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

    # Follows recognised faces between frames so identities are not recomputed every frame.
    from engine.people import Tracker
    tracker = Tracker(targets) if targets is not None else None
    previous_frame = None

    # Steadies landmarks and masks between frames; a single photo has no previous frame.
    from engine.stabilize import Stabilizer
    stabilizer = Stabilizer() if config['mode'] != 'image' else None

    def analyze(frame):
        """CPU side: find faces and decide who gets which source."""
        # Only the source needs a recognition embedding. Target faces need landmarks.
        found = detect(frame)
        states = stabilizer.landmarks(found) if stabilizer is not None else [None] * len(found)
        state_of = {id(face): state for face, state in zip(found, states)}
        if config.get('many_faces', False):
            pairs = [(face, source) for face in found]
        elif targets is not None:
            # A scene cut can put another person where someone stood a frame ago.
            nonlocal previous_frame
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (32, 18), interpolation=cv2.INTER_AREA).astype(np.int16)
            if previous_frame is not None and np.abs(small - previous_frame).mean() > 25:
                tracker.reset()
            previous_frame = small

            def embed(face):
                recognizer.get(frame, face)
                return face.normed_embedding
            pairs = [(found[i], person_sources[p]) for i, p in tracker.assign(found, embed)]
        else:
            pairs = [(face, source) for face in sorted(found, key=lambda f: f.bbox[0])[:1]]
        return [(face, face_source, state_of[id(face)]) for face, face_source in pairs]

    def render(frame, pairs):
        """GPU side: generate and paste the faces chosen by analyze()."""
        for target_face, face_source, state in pairs:
            fake, M = swapper.get(frame, target_face, face_source, paste_back=False)
            smooth = (lambda mask, state=state: stabilizer.mask(state, mask)) if state is not None else None
            frame = blender.paste(frame, fake, M, smooth)
        return frame, len(pairs)

    def transform(frame):
        return render(frame, analyze(frame))

    mode = config['mode']
    if mode == 'image':
        frame = cv2.imdecode(np.fromfile(config['target'], dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError('Hedef fotoğraf okunamadı.')
        frame, count = transform(frame)
        if not count:
            raise ValueError('Seçilen kişi hedef fotoğrafta bulunamadı.' if targets is not None
                             else 'Hedef fotoğrafta yüz bulunamadı. Başka bir fotoğraf seçin.')
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
    recording = mode == 'live' and bool(config.get('output'))
    if recording and not ffmpeg:
        raise ValueError('Canlı görüntüyü kaydetmek için FFmpeg kurulmalıdır.')
    # The supervisor asks a recording live job to finish by creating this file,
    # so the MP4 is closed properly instead of being cut off by a kill.
    stop_file = Path(os.environ['DLC_JOB_DIR']) / 'stop' if os.environ.get('DLC_JOB_DIR') else None
    record_fps, written, record_start, camera_lost = 30, 0, 0.0, False
    microphone, microphone_warned = None, False
    if mode == 'live':
        # Tests replay a file instead of opening a real camera.
        fake = os.environ.get('DLC_FAKE_CAMERA')
        cap = FakeCamera(fake) if fake else cv2.VideoCapture(config.get('camera', 0), camera_api(cv2))
    else:
        cap = cv2.VideoCapture(config['target'])
    encoder = None
    temp_dir = None
    virtual_camera = None
    try:
        if not cap.isOpened():
            raise ValueError('Kamera açılamadı. Kamera numarasını ve kamera izinlerini kontrol edin.' if mode == 'live' else 'Video açılamadı. Dosya biçimini kontrol edin.')
        if mode == 'live':
            width, height = config.get('camera_size') or CAMERA_SIZES[1]
            if sys.platform == 'win32':
                # DirectShow delivers HD at full frame rate only as MJPG; YUY2 drops to ~5 fps.
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            actual = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            # Drivers often ignore BUFFERSIZE; draining on a thread keeps processing
            # on the newest frame instead of a growing backlog.
            cap = LatestFrameReader(cap)
            phase(f'Kamera açık ({actual[0]}×{actual[1]}). Canlı görüntü işleniyor.')
        else:
            phase('Video işleniyor…')
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if 0 < fps <= 240 else 25.0
        total = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))) if mode == 'video' else 0
        frames = 0
        start = time.monotonic()
        # Two stages: a thread reads and analyses the next frame (CPU detection,
        # recognition) while this thread renders the current one (GPU swap, mask,
        # outputs). ONNX Runtime releases the GIL, so both really run at once.
        import queue
        import threading
        handoff = queue.Queue(maxsize=2)
        halt = threading.Event()

        def deliver(item):
            while not halt.is_set():
                try:
                    handoff.put(item, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def produce():
            try:
                while not halt.is_set():
                    if mode == 'live' and stop_file is not None and stop_file.exists():
                        return deliver(('stop', None))
                    ok, frame = cap.read()
                    if not ok:
                        return deliver(('end', None))
                    if mode == 'live' and config.get('mirror', True):
                        frame = cv2.flip(frame, 1)
                    deliver(('frame', (frame, analyze(frame))))
            except BaseException as error:  # surfaced on the main thread
                deliver(('error', error))

        producer = threading.Thread(target=produce, daemon=True)
        producer.start()
        while True:
            kind, item = handoff.get()
            if kind == 'error':
                raise item
            if kind == 'stop':
                break
            if kind == 'end':
                if recording and encoder is not None:
                    camera_lost = True  # keep what was recorded so far
                    break
                if mode == 'live':
                    raise ValueError('Kamera görüntüsü kesildi. Bağlantıyı kontrol edip yeniden başlatın.')
                break
            frame, count = render(*item)
            frames += 1
            # The mirror is only for the local preview; outputs carry the true image.
            true_frame = cv2.flip(frame, 1) if mode == 'live' and config.get('mirror', True) else frame
            if mode == 'live' and config.get('virtual_camera'):
                if virtual_camera is None:
                    from engine.virtualcam import open_camera
                    virtual_camera = open_camera(frame.shape[1], frame.shape[0])
                    phase(f'Sanal kamera açık. Görüntülü görüşmede "{virtual_camera.name}" kamerasını seçin.')
                # Meeting apps mirror their own self-view; others must see the true image.
                virtual_camera.send(true_frame)
            if mode == 'video' or recording:
                if encoder is None:
                    # Same-volume temporary output; removed even when the process is killed by supervisor.
                    temp_dir = tempfile.TemporaryDirectory(prefix='yuz-atolyesi-', dir=os.environ.get('DLC_JOB_DIR'))
                    video_path = Path(temp_dir.name) / 'silent.mp4'
                    h, w = frame.shape[:2]
                    encoder = subprocess.Popen([ffmpeg, '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(record_fps if recording else fps), '-i', '-', '-an', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video_path)], stdin=subprocess.PIPE, **SUBPROCESS_FLAGS)
                    record_start = time.monotonic()
                    if recording and config.get('microphone'):
                        from engine.audio import Microphone
                        microphone = Microphone(ffmpeg, config['microphone'], Path(temp_dir.name) / 'audio.m4a')
                if microphone is not None and not microphone_warned and microphone.failed():
                    microphone_warned = True
                    phase('Mikrofon açılamadı; kayıt sessiz devam ediyor. Mikrofon iznini ve seçimini kontrol edin.')
                if recording:
                    # The engine runs slower than 30 fps and unevenly; repeating frames keeps
                    # the recording in real time (capped so a stall does not flood the encoder).
                    due = min(int((time.monotonic() - record_start) * record_fps) + 1 - written, record_fps)
                    for _ in range(max(due, 0)):
                        encoder.stdin.write(true_frame.tobytes())
                    written += max(due, 0)
                else:
                    encoder.stdin.write(frame.tobytes())
            preview(frame, fps=round(frames / max(0.01, time.monotonic() - start), 1), progress=min(99, round(frames / total * 100, 1)) if total else None, faces=count)
        if not frames and mode == 'video':
            raise ValueError('Videoda okunabilir kare bulunamadı.')
        if recording and encoder is not None:
            phase('Canlı kayıt kaydediliyor…')
            encoder.stdin.close()
            if encoder.wait(timeout=90) != 0:
                raise ValueError('Canlı kayıt kodlanamadı. Diskte yeterli boş alan olduğundan emin olun.')
            message = 'Canlı kayıt kaydedildi.'
            if microphone is not None:
                from engine.audio import join
                joined = Path(temp_dir.name) / 'result.mp4'
                if microphone.stop() and join(ffmpeg, video_path, microphone.path, microphone.started, record_start, joined):
                    video_path = joined
                else:
                    message = 'Canlı kayıt sessiz kaydedildi; mikrofon sesi alınamadı.'
            publish(config['output'], source=video_path)
            emit('complete', output=config['output'], message=message)
            if camera_lost:
                raise ValueError('Kamera görüntüsü kesildi; o ana kadarki kayıt kaydedildi.')
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
        if 'halt' in locals():
            halt.set()
            producer.join(timeout=5)
        cap.release()
        if virtual_camera is not None:
            virtual_camera.close()
        if microphone is not None:
            microphone.kill()
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
