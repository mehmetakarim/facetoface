"""Opt-in: send synthetic bars, never open a physical camera."""
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from engine.virtualcam import open_camera

if sys.platform != 'darwin':
    raise SystemExit('Bu test macOS içindir.')
frame = np.zeros((480, 640, 3), dtype=np.uint8)
frame[:, :213] = (255, 0, 0)
frame[:, 213:426] = (0, 255, 0)
frame[:, 426:] = (0, 0, 255)
try:
    camera = open_camera(640, 480)
except ValueError as error:
    raise SystemExit(str(error)) from None
print('15 saniyelik test: soldan sağa mavi, yeşil, kırmızı. OBS Virtual Camera’yı seçin.', flush=True)
try:
    until = time.monotonic() + 15
    while time.monotonic() < until:
        camera.send(frame)
        time.sleep(1 / 30)
finally:
    camera.close()
print('Aktarım durduruldu.')
