"""Feed processed frames to a virtual camera on Windows.

Two targets share one shared-memory queue layout (obs-studio
plugins/win-dshow/shared-memory-queue.c): a header followed by three NV12 frame
slots; the writer bumps write_idx, fills a slot and publishes it via read_idx.

- Windows 11: our own Media Foundation camera ("Yüz Atölyesi Kamera", built from
  native/vcam). yuz-vcam.exe keeps it registered while the job runs; its media
  source runs inside the Frame Server service and creates the Global mapping we
  write to. Media Foundation apps such as WhatsApp and the Camera app see it.
- Otherwise: the OBS Virtual Camera DirectShow filter, which only DirectShow apps
  (browsers, Zoom, Discord, OBS) see. OBS must be installed but need not run.
"""
import ctypes
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

QUEUE_NAME = 'OBSVirtualCamVideo'
FILTER_CLSID = '{A3FCE0F5-3493-419F-958A-ABA1250EC20B}'
NATIVE_QUEUE_NAME = 'Global\\YuzAtolyesiKamera'
NATIVE_CLSID = '{92966083-168A-4874-9B2F-4E4F50BD7742}'  # native/vcam/source/dllmain.cpp
NATIVE_SIZE = (1280, 960)  # native/vcam/source/SharedFrames.h
STATE_STARTING, STATE_READY, STATE_STOPPING = 1, 2, 3
# write_idx, read_idx, state, offsets[3], type, cx, cy, interval(u64), reserved[8].
# MSVC aligns the uint64 interval to 8 bytes, leaving 4 bytes of padding before it;
# without them OBS reads a zero interval and divides by it.
HEADER = struct.Struct('<3I3I3I4xQ8I')
FRAME_HEADER_SIZE = 32  # holds the frame timestamp
FILE_MAP_WRITE, FILE_MAP_READ = 0x0002, 0x0004
HELPER_ERRORS = {
    3: 'Bu Windows sürümü yerleşik sanal kamerayı desteklemiyor; Windows 11 gerekir.',
    4: 'Yüz Atölyesi Kamera kurulu değil. Ayarlardan sanal kamerayı kurun.',
}


def _align(size):
    return (size + 31) & ~31


def _layout(width, height):
    frame_size = width * height * 3 // 2
    offsets, size = [], _align(HEADER.size)
    for _ in range(3):
        offsets.append(size)
        size = _align(size + FRAME_HEADER_SIZE + frame_size)
    return offsets, size, frame_size


def _kernel32():
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateFileMappingW.restype = ctypes.c_void_p
    kernel32.CreateFileMappingW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p]
    kernel32.MapViewOfFile.restype = ctypes.c_void_p
    kernel32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                       ctypes.c_uint32, ctypes.c_size_t]
    kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel32


def _nv12(frame, width, height):
    import cv2
    import numpy as np
    if frame.shape[1] != width or frame.shape[0] != height:
        frame = cv2.resize(frame, (width, height))
    i420 = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420).reshape(-1)
    pixels = width * height
    quarter = pixels // 4
    nv12 = np.empty(pixels * 3 // 2, np.uint8)
    nv12[:pixels] = i420[:pixels]
    nv12[pixels::2] = i420[pixels:pixels + quarter]
    nv12[pixels + 1::2] = i420[pixels + quarter:]
    return nv12


def _letterbox(frame, width, height):
    """Scale into a fixed canvas without distorting the face."""
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    scale = min(width / w, height / h)
    fit = cv2.resize(frame, (round(w * scale) & ~1, round(h * scale) & ~1))
    if fit.shape[:2] == (height, width):
        return fit
    canvas = np.zeros((height, width, 3), np.uint8)
    y, x = (height - fit.shape[0]) // 2, (width - fit.shape[1]) // 2
    canvas[y:y + fit.shape[0], x:x + fit.shape[1]] = fit
    return canvas


class _Queue:
    """Writer side of one mapped queue."""

    def __init__(self, kernel32, handle, width, height, fps):
        self.kernel32, self.handle = kernel32, handle
        self.width, self.height = width, height
        self.offsets, size, self.frame_size = _layout(width, height)
        self.view = kernel32.MapViewOfFile(handle, FILE_MAP_WRITE | FILE_MAP_READ, 0, 0, size)
        if not self.view:
            kernel32.CloseHandle(handle)
            raise ValueError('Sanal kamera başlatılamadı.')
        self.memory = (ctypes.c_uint8 * size).from_address(self.view)
        self.index = 0
        HEADER.pack_into(self.memory, 0, 0, 0, STATE_STARTING, *self.offsets, 0,
                         width, height, round(10_000_000 / fps), *[0] * 8)

    def send(self, frame):
        nv12 = _nv12(frame, self.width, self.height)
        self.index += 1
        slot = self.offsets[self.index % 3]
        struct.pack_into('<I', self.memory, 0, self.index)  # write_idx
        # perf_counter_ns() is QueryPerformanceCounter on Windows: the clock the native
        # source uses to drop stale frames (and the one OBS stamps with). Before
        # Python 3.13, monotonic_ns() is GetTickCount64 and seconds off from it.
        struct.pack_into('<Q', self.memory, slot, time.perf_counter_ns())
        ctypes.memmove(self.view + slot + FRAME_HEADER_SIZE, nv12.ctypes.data, self.frame_size)
        struct.pack_into('<II', self.memory, 4, self.index, STATE_READY)  # read_idx, state

    def close(self):
        if not self.view:
            return
        struct.pack_into('<I', self.memory, 8, STATE_STOPPING)
        self.memory = None
        self.kernel32.UnmapViewOfFile(self.view)
        self.kernel32.CloseHandle(self.handle)
        self.view = None


def installed():
    """OBS Virtual Camera (DirectShow) is registered."""
    if sys.platform != 'win32':
        return False
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf'CLSID\{FILTER_CLSID}\InprocServer32'))
        return True
    except OSError:
        return False


def helper_path():
    root = Path(os.environ.get('DLC_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
    for candidate in (root / 'vcam' / 'yuz-vcam.exe', root / 'native' / 'vcam' / 'bin' / 'yuz-vcam.exe'):
        if candidate.is_file():
            return candidate
    return None


def native_available():
    """Windows 11 and the camera files ship with this build, installed or not."""
    if sys.platform != 'win32' or sys.getwindowsversion().build < 22000:
        return False
    helper = helper_path()
    return bool(helper) and (helper.parent / 'YuzAtolyesiKamera.dll').is_file()


def status():
    return {'native_available': native_available(), 'native_camera': native_installed(),
            'obs_camera': installed()}


def native_installed():
    """Windows 11 with our media source registered machine-wide and the helper present."""
    if sys.platform != 'win32' or sys.getwindowsversion().build < 22000 or not helper_path():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf'SOFTWARE\Classes\CLSID\{NATIVE_CLSID}\InprocServer32') as key:
            return Path(winreg.QueryValue(key, None)).is_file()
    except OSError:
        return False


class VirtualCamera:
    """OBS Virtual Camera: we create the queue the DirectShow filter reads."""
    name = 'OBS Virtual Camera'

    def __init__(self, width, height, fps=30):
        if not installed():
            raise ValueError('Sanal kamera için OBS Studio kurulmalıdır. OBS kurulduktan sonra yeniden deneyin.')
        kernel32 = _kernel32()
        # NV12 needs even dimensions; frames are resized to these.
        width, height = width & ~1, height & ~1
        existing = kernel32.OpenFileMappingW(FILE_MAP_READ, False, QUEUE_NAME)
        if existing:
            kernel32.CloseHandle(existing)
            raise ValueError('Sanal kamera başka bir uygulama tarafından kullanılıyor. OBS’de sanal kamerayı durdurup yeniden deneyin.')
        size = _layout(width, height)[1]
        handle = kernel32.CreateFileMappingW(ctypes.c_void_p(-1), None, 0x04, 0, size, QUEUE_NAME)
        if not handle:
            raise ValueError('Sanal kamera başlatılamadı.')
        self.queue = _Queue(kernel32, handle, width, height, fps)
        self.width, self.height = width, height
        self.offsets, self.frame_size = self.queue.offsets, self.queue.frame_size

    def send(self, frame):
        self.queue.send(frame)

    def close(self):
        self.queue.close()


class WindowsCamera:
    """Windows 11 Media Foundation camera; the native source owns the queue."""
    name = 'Yüz Atölyesi Kamera'

    def __init__(self, fps=30):
        self.fps = fps
        self.queue = None
        self.last_attempt = 0.0
        self.process = subprocess.Popen([str(helper_path())], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        first = []
        reader = threading.Thread(target=lambda: first.append(self.process.stdout.readline().strip()), daemon=True)
        reader.start()
        reader.join(timeout=15)
        if first[:1] != ['ready']:
            self.close()
            code = self.process.returncode
            raise ValueError(HELPER_ERRORS.get(code, f'Sanal kamera başlatılamadı ({first[0] if first else "zaman aşımı"}).'))

    def send(self, frame):
        if self.queue is None:
            # The mapping exists only once an app streams from the camera; until then
            # it shows its placeholder and frames have nowhere to go.
            if time.monotonic() - self.last_attempt < 1:
                return
            self.last_attempt = time.monotonic()
            kernel32 = _kernel32()
            handle = kernel32.OpenFileMappingW(FILE_MAP_WRITE | FILE_MAP_READ, False, NATIVE_QUEUE_NAME)
            if not handle:
                return
            self.queue = _Queue(kernel32, handle, *NATIVE_SIZE, self.fps)
        self.queue.send(_letterbox(frame, *NATIVE_SIZE))

    def close(self):
        if self.queue is not None:
            self.queue.close()
            self.queue = None
        if self.process.poll() is None:
            self.process.stdin.close()  # the helper removes the camera when stdin closes
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def open_camera(width, height):
    """Prefer the camera every app can see; fall back to OBS."""
    if native_installed():
        return WindowsCamera()
    return VirtualCamera(width, height)
