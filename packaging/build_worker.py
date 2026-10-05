"""Keep raw InsightFace sources for the private inference namespace."""
from PyInstaller.__main__ import run
run(['engine/worker.py', '--name=engine-worker', '--onedir', '--clean', '--noconfirm',
     '--paths=.', '--collect-all=insightface', '--copy-metadata=insightface',
     '--collect-all=onnxruntime', '--collect-all=cv2_enumerate_cameras', '--collect-all=imageio_ffmpeg',
     '--hidden-import=engine.inference', '--hidden-import=engine.blend', '--hidden-import=engine.protocol',
     '--hidden-import=engine.output'])

# Preserve installed distributions' license/notice metadata in the portable kit.
from importlib import metadata
from pathlib import Path
import shutil
notice_root = Path('dist/engine-worker/third-party')
for distribution in metadata.distributions():
    for item in distribution.files or []:
        name = str(item).lower()
        if any(word in name for word in ('license', 'copying', 'notice')) or name.endswith('.dist-info/metadata'):
            source = Path(distribution.locate_file(item))
            if source.is_file():
                relative = Path(*[part for part in Path(item).parts if part not in ('..', '.')])
                target = notice_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
