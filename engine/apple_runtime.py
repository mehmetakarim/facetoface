"""CoreML configuration for the pinned macOS runtime."""
import atexit
import hashlib
import os
import shutil
from pathlib import Path
import tempfile


def coreml_options(model_path, runtime_version):
    if tuple(int(part) for part in runtime_version.split('.')[:2]) < (1, 23):
        raise ValueError('Apple hızlandırması için ONNX Runtime güncellemesi gerekiyor. macOS motor bağımlılıklarını yeniden kurun.')
    model = Path(model_path).resolve()
    stat = model.stat()
    # A replaced model or changed runtime must never reuse an old compiled graph.
    identity = f'{model}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}:{runtime_version}:MLProgram:ALL:v1'
    key = hashlib.sha256(identity.encode()).hexdigest()[:32]
    root = Path(os.environ.get('DLC_COREML_CACHE') or
                Path(os.environ.get('XDG_CACHE_HOME', Path.home() / 'Library' / 'Caches')) / 'yuz-atolyesi-coreml')
    cache = root / key
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError('Apple hızlandırması önbelleği oluşturulamadı. Önbellek konumunun yazılabilir olduğunu ve diskte boş alan bulunduğunu kontrol edin.') from exc
    if shutil.disk_usage(cache).free < 3 * 1024 ** 3:
        raise ValueError('Apple hızlandırması için önbellek diskinde en az 3 GB boş alan gerekir. Yer açın veya Standart işlem yöntemini seçin.')
    return {'ModelFormat': 'MLProgram', 'MLComputeUnits': 'ALL',
            'RequireStaticInputShapes': '0', 'ModelCacheDirectory': str(cache)}


def prepare_coreml_temp():
    # Use the supervisor's disposable job directory so forced cancellation also
    # removes Apple's temporary compiled fragments. Persistent cache is separate.
    job = os.environ.get('DLC_JOB_DIR')
    scratch = Path(job) / 'coreml' if job else Path(tempfile.mkdtemp(prefix='yuz-coreml-'))
    try:
        scratch.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError('Apple hızlandırması için geçici klasör oluşturulamadı. Disk alanını kontrol edin.') from exc
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    os.environ['TMPDIR'] = str(scratch)
    tempfile.tempdir = str(scratch)
