"""Nonblocking, bounded transport to our signed CMIO sink-stream client."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading


def manager_path():
    root = Path(os.environ.get('DLC_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
    for app in (Path('/Applications/YuzAtolyesiCamera.app'), root / 'vcam' / 'YuzAtolyesiCamera.app',
                root / 'native' / 'macos-camera' / 'build' / 'YuzAtolyesiCamera.app'):
        if (app / 'Contents' / 'MacOS' / 'yuz-camera-bridge').is_file():
            return app
    return None


def helper_path():
    app = manager_path()
    return app / 'Contents' / 'MacOS' / 'yuz-camera-bridge' if app else None


def installed():
    if sys.platform != 'darwin':
        return False
    helper = helper_path()
    if not helper:
        return False
    try:
        result = subprocess.run([str(helper), '--status'], capture_output=True, text=True, timeout=5, check=True)
        return json.loads(result.stdout).get('installed') is True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def encode_frame(frame):
    import cv2
    from engine.virtualcam import _letterbox
    return cv2.cvtColor(_letterbox(frame, 640, 480), cv2.COLOR_BGR2BGRA).tobytes()


class MacNativeCamera:
    name = 'Yüz Atölyesi Kamera'

    def __init__(self, width, height):
        helper = helper_path()
        if not helper:
            raise ValueError('Yerel kamera bileşeni bulunamadı. İmzalı Yüz Atölyesi Kamera paketini kurun.')
        self.condition = threading.Condition()
        self.pending = None
        self.closed = False
        self.failed = False
        self.thread = None
        self.process = subprocess.Popen([str(helper), '--send'], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        try:
            ready, _, _ = select.select([self.process.stdout], [], [], 10)
            if not ready or self.process.stdout.readline() != b'READY\n':
                raise ValueError('Yerel kamera açılamadı. Kamera uzantısını etkinleştirip başka bir aktarımın açık olmadığını kontrol edin.')
            self.thread = threading.Thread(target=self._write, daemon=True)
            self.thread.start()
        except BaseException:
            self.close()
            raise

    def _write(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.pending is not None)
                    if self.closed:
                        return
                    data, self.pending = self.pending, None
                # Raw pipes may perform partial writes. Preserve frame boundaries.
                remaining = memoryview(data)
                while remaining:
                    count = self.process.stdin.write(remaining)
                    if not count:
                        raise BrokenPipeError()
                    remaining = remaining[count:]
        except (OSError, ValueError):
            with self.condition:
                self.failed = True
                self.pending = None

    def send(self, frame):
        data = encode_frame(frame)
        with self.condition:
            if self.closed or self.failed or self.process.poll() is not None:
                raise ValueError('Yerel kamera aktarımı durdu. Canlı görüntüyü yeniden başlatın.')
            # Keep only the newest frame while the helper is busy.
            self.pending = data
            self.condition.notify()

    def close(self):
        with self.condition:
            if self.closed:
                return
            self.closed = True
            self.pending = None
            self.condition.notify_all()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.thread:
            self.thread.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
