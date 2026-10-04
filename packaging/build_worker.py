"""Keep raw InsightFace sources for the private inference namespace."""
from PyInstaller.__main__ import run
run(['engine/worker.py', '--name=engine-worker', '--onedir', '--clean', '--noconfirm',
     '--paths=.', '--collect-all=insightface', '--copy-metadata=insightface',
     '--collect-all=onnxruntime', '--collect-all=imageio_ffmpeg',
     '--hidden-import=engine.inference', '--hidden-import=engine.protocol',
     '--hidden-import=engine.output'])
