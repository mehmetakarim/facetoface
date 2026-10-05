"""Small, dependency-free protocol shared by the worker and its tests."""
import json
from pathlib import Path

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm'}


def validate(config):
    mode = config.get('mode')
    if mode not in {'diagnostics', 'source', 'image', 'video', 'live'}:
        raise ValueError('Geçersiz çalışma modu.')
    if mode == 'diagnostics':
        return config
    source = Path(config.get('source') or '')
    if not source.is_file() or source.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError('Kaynak yüz için geçerli bir fotoğraf seçin.')
    if config.get('provider', 'cpu') not in {'cpu', 'coreml', 'directml'}:
        raise ValueError('Geçersiz işlem sağlayıcısı.')
    if type(config.get('occlusion', True)) is not bool:
        raise ValueError('Geçersiz el ve nesne koruması ayarı.')
    if mode == 'live':
        camera = config.get('camera', 0)
        if type(camera) is not int or not 0 <= camera <= 9:
            raise ValueError('Kamera numarası 0 ile 9 arasında olmalıdır.')
    if mode in {'image', 'video'}:
        target = Path(config.get('target') or '')
        allowed = IMAGE_EXTENSIONS if mode == 'image' else VIDEO_EXTENSIONS
        if not target.is_file() or target.suffix.lower() not in allowed:
            raise ValueError('İşlemek istediğiniz fotoğrafı veya videoyu seçin.')
        output = Path(config.get('output') or '')
        if not str(config.get('output') or '').strip() or not output.parent.is_dir():
            raise ValueError('Sonucun kaydedileceği geçerli bir konum seçin.')
        if output.resolve() in {source.resolve(), target.resolve()}:
            raise ValueError('Sonucu kaynak dosyanın üzerine kaydedemezsiniz. Farklı bir ad seçin.')
        if output.exists():
            raise ValueError('Bu adda bir dosya zaten var. Farklı bir ad seçin.')
        if output.suffix.lower() not in ({'.png', '.jpg', '.jpeg'} if mode == 'image' else {'.mp4'}):
            raise ValueError('Fotoğrafı PNG veya JPEG, videoyu MP4 olarak kaydedin.')
    return config


def encode(event):
    return json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n'
