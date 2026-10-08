"""Small, dependency-free protocol shared by the worker and its tests."""
import json
from pathlib import Path

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm'}
EMBEDDING_SIZE = 512  # w600k_r50 output
MAX_SELECTED_FACES = 8
CAMERA_SIZES = [(640, 480), (1280, 720), (1920, 1080)]  # default: 1280x720


def validate_camera(config):
    camera = config.get('camera', 0)
    if type(camera) is not int or not 0 <= camera <= 9:
        raise ValueError('Kamera numarası 0 ile 9 arasında olmalıdır.')
    size = config.get('camera_size')
    if size is not None and (type(size) is not list or tuple(size) not in CAMERA_SIZES):
        raise ValueError('Geçersiz kamera çözünürlüğü.')


def validate(config):
    mode = config.get('mode')
    if mode not in {'diagnostics', 'cameras', 'target_faces', 'source', 'image', 'video', 'live'}:
        raise ValueError('Geçersiz çalışma modu.')
    if mode in {'diagnostics', 'cameras'}:
        return config
    if mode == 'target_faces':
        # Finds the people in a target file, or in the camera when no target is given.
        if not config.get('target'):
            validate_camera(config)
            return config
        target = Path(config['target'])
        if not target.is_file() or target.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            raise ValueError('Kişileri bulmak için geçerli bir fotoğraf veya video seçin.')
        return config
    selected = config.get('target_embeddings', [])
    if (type(selected) is not list or len(selected) > MAX_SELECTED_FACES
            or any(type(e) is not list or len(e) != EMBEDDING_SIZE
                   or not all(type(v) in (int, float) for v in e) for e in selected)):
        raise ValueError('Geçersiz kişi seçimi. Hedefteki kişileri yeniden bulun.')
    # Optional per-person source photos, aligned with target_embeddings; None = main source.
    sources = config.get('target_sources', [])
    if type(sources) is not list or (sources and len(sources) != len(selected)):
        raise ValueError('Geçersiz kişi seçimi. Hedefteki kişileri yeniden bulun.')
    for number, path in enumerate(sources, 1):
        if path is not None and (type(path) is not str or not Path(path).is_file()
                                 or Path(path).suffix.lower() not in IMAGE_EXTENSIONS):
            raise ValueError(f'{number}. kişi için geçerli bir kaynak fotoğraf seçin.')
    source = Path(config.get('source') or '')
    if not source.is_file() or source.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError('Kaynak yüz için geçerli bir fotoğraf seçin.')
    if config.get('provider', 'cpu') not in {'cpu', 'coreml', 'directml'}:
        raise ValueError('Geçersiz işlem sağlayıcısı.')
    if type(config.get('occlusion', True)) is not bool:
        raise ValueError('Geçersiz el ve nesne koruması ayarı.')
    if type(config.get('virtual_camera', False)) is not bool:
        raise ValueError('Geçersiz sanal kamera ayarı.')
    if mode == 'live':
        validate_camera(config)
        # Recording the live view is optional: no output means preview only.
        if config.get('output') is not None:
            validate_output(config, [source], {'.mp4'})
        microphone = config.get('microphone')
        if microphone is not None and (type(microphone) is not str or not 0 < len(microphone) <= 512):
            raise ValueError('Geçersiz mikrofon seçimi. Mikrofon listesini yenileyin.')
    if mode in {'image', 'video'}:
        target = Path(config.get('target') or '')
        allowed = IMAGE_EXTENSIONS if mode == 'image' else VIDEO_EXTENSIONS
        if not target.is_file() or target.suffix.lower() not in allowed:
            raise ValueError('İşlemek istediğiniz fotoğrafı veya videoyu seçin.')
        validate_output(config, [source, target], {'.png', '.jpg', '.jpeg'} if mode == 'image' else {'.mp4'})
    return config


def validate_output(config, inputs, suffixes):
    output = Path(config.get('output') or '')
    if not str(config.get('output') or '').strip() or not output.parent.is_dir():
        raise ValueError('Sonucun kaydedileceği geçerli bir konum seçin.')
    if output.resolve() in {path.resolve() for path in inputs}:
        raise ValueError('Sonucu kaynak dosyanın üzerine kaydedemezsiniz. Farklı bir ad seçin.')
    if output.exists():
        raise ValueError('Bu adda bir dosya zaten var. Farklı bir ad seçin.')
    if output.suffix.lower() not in suffixes:
        raise ValueError('Fotoğrafı PNG veya JPEG, videoyu MP4 olarak kaydedin.')


def encode(event):
    return json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n'
