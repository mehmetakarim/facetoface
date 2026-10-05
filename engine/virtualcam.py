"""Feed processed frames to the OBS Virtual Camera on Windows.

OBS registers a DirectShow filter ("OBS Virtual Camera") that reads frames from a
named shared-memory queue. This writer implements that queue layout
(obs-studio plugins/win-dshow/shared-memory-queue.c): a header followed by three
NV12 frame slots; the writer bumps write_idx, fills a slot and publishes it via
read_idx. OBS itself does not need to be running.
"""
import ctypes
import struct
import sys
import time

QUEUE_NAME = 'OBSVirtualCamVideo'
FILTER_CLSID = '{A3FCE0F5-3493-419F-958A-ABA1250EC20B}'
STATE_STARTING, STATE_READY, STATE_STOPPING = 1, 2, 3
# write_idx, read_idx, state, offsets[3], type, cx, cy, interval(u64), reserved[8].
# MSVC aligns the uint64 interval to 8 bytes, leaving 4 bytes of padding before it;
# without them OBS reads a zero interval and divides by it.
HEADER = struct.Struct('<3I3I3I4xQ8I')
FRAME_HEADER_SIZE = 32  # holds the frame timestamp


def _align(size):
    return (size + 31) & ~31


def installed():
    if sys.platform != 'win32':
        return False
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf'CLSID\{FILTER_CLSID}\InprocServer32'))
        return True
    except OSError:
        return False


class VirtualCamera:
    def __init__(self, width, height, fps=30):
        if not installed():
            raise ValueError('Sanal kamera için OBS Studio kurulmalıdır. OBS kurulduktan sonra yeniden deneyin.')
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
        self.kernel32 = kernel32
        # NV12 needs even dimensions; callers crop to these.
        self.width, self.height = width & ~1, height & ~1
        frame_size = self.width * self.height * 3 // 2
        offsets, size = [], _align(HEADER.size)
        for _ in range(3):
            offsets.append(size)
            size = _align(size + FRAME_HEADER_SIZE + frame_size)
        existing = kernel32.OpenFileMappingW(0x0004, False, QUEUE_NAME)  # FILE_MAP_READ
        if existing:
            kernel32.CloseHandle(existing)
            raise ValueError('Sanal kamera başka bir uygulama tarafından kullanılıyor. OBS’de sanal kamerayı durdurup yeniden deneyin.')
        self.handle = kernel32.CreateFileMappingW(ctypes.c_void_p(-1), None, 0x04, 0, size, QUEUE_NAME)
        if not self.handle:
            raise ValueError('Sanal kamera başlatılamadı.')
        self.view = kernel32.MapViewOfFile(self.handle, 0x0002 | 0x0004, 0, 0, 0)  # read/write
        if not self.view:
            kernel32.CloseHandle(self.handle)
            raise ValueError('Sanal kamera başlatılamadı.')
        self.memory = (ctypes.c_uint8 * size).from_address(self.view)
        self.offsets = offsets
        self.frame_size = frame_size
        self.index = 0
        HEADER.pack_into(self.memory, 0, 0, 0, STATE_STARTING, *offsets, 0,
                         self.width, self.height, round(10_000_000 / fps), *[0] * 8)

    def send(self, frame):
        import cv2
        import numpy as np
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))
        i420 = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
        pixels = self.width * self.height
        quarter = pixels // 4
        nv12 = np.empty(pixels * 3 // 2, np.uint8)
        nv12[:pixels] = i420.reshape(-1)[:pixels]
        nv12[pixels::2] = i420.reshape(-1)[pixels:pixels + quarter]
        nv12[pixels + 1::2] = i420.reshape(-1)[pixels + quarter:]
        self.index += 1
        slot = self.offsets[self.index % 3]
        struct.pack_into('<I', self.memory, 0, self.index)  # write_idx
        struct.pack_into('<Q', self.memory, slot, time.monotonic_ns())
        ctypes.memmove(self.view + slot + FRAME_HEADER_SIZE, nv12.ctypes.data, self.frame_size)
        struct.pack_into('<II', self.memory, 4, self.index, STATE_READY)  # read_idx, state

    def close(self):
        if not getattr(self, 'view', None):
            return
        struct.pack_into('<I', self.memory, 8, STATE_STOPPING)
        self.memory = None
        self.kernel32.UnmapViewOfFile(self.view)
        self.kernel32.CloseHandle(self.handle)
        self.view = None
