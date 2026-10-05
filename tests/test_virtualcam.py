import mmap
import sys
import unittest
from unittest import mock

import numpy as np

from engine import virtualcam


@unittest.skipUnless(sys.platform == 'win32', 'OBS shared-memory queue is Windows-only')
class VirtualCameraQueueTests(unittest.TestCase):
    def test_nv12_frame_is_published_in_obs_layout(self):
        import cv2
        with mock.patch.object(virtualcam, 'installed', return_value=True):
            camera = virtualcam.VirtualCamera(641, 481)  # odd sizes are trimmed to even
        self.addCleanup(camera.close)
        frame = np.zeros((480, 640, 3), np.uint8)
        frame[:, :320] = (255, 0, 0)  # blue left half, red right half
        frame[:, 320:] = (0, 0, 255)
        camera.send(frame)
        size = camera.offsets[-1] + virtualcam.FRAME_HEADER_SIZE + camera.frame_size
        reader = mmap.mmap(-1, size, tagname=virtualcam.QUEUE_NAME, access=mmap.ACCESS_READ)
        self.addCleanup(reader.close)
        header = virtualcam.HEADER.unpack_from(reader, 0)
        write_idx, read_idx, state, *offsets = header[:6]
        cx, cy, interval = header[7], header[8], header[9]
        self.assertEqual((write_idx, read_idx, state), (1, 1, virtualcam.STATE_READY))
        self.assertEqual((cx, cy, interval), (640, 480, 333333))
        start = offsets[1] + virtualcam.FRAME_HEADER_SIZE
        nv12 = np.frombuffer(reader, np.uint8, camera.frame_size, start).reshape(720, 640)
        bgr = cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
        np.testing.assert_allclose(bgr[240, 100], (255, 0, 0), atol=6)
        np.testing.assert_allclose(bgr[240, 500], (0, 0, 255), atol=6)
        camera.close()
        self.assertEqual(virtualcam.HEADER.unpack_from(reader, 0)[2], virtualcam.STATE_STOPPING)

    def test_frames_are_stamped_with_the_performance_counter(self):
        # native/vcam/source/SharedFrames.cpp drops frames whose QPC stamp is stale.
        import struct
        import time
        with mock.patch.object(virtualcam, 'installed', return_value=True):
            camera = virtualcam.VirtualCamera(64, 48)
        self.addCleanup(camera.close)
        before = time.perf_counter_ns()
        camera.send(np.zeros((48, 64, 3), np.uint8))
        stamp = struct.unpack_from('<Q', camera.queue.memory, camera.offsets[1])[0]
        self.assertTrue(before <= stamp <= time.perf_counter_ns())

    def test_header_matches_obs_c_struct(self):
        # struct queue_header: the uint64 interval sits at offset 40 after MSVC padding.
        self.assertEqual(virtualcam.HEADER.size, 80)
        data = bytearray(80)
        virtualcam.HEADER.pack_into(data, 0, *range(9), 0xAABBCCDD, *[0] * 8)
        self.assertEqual(int.from_bytes(data[40:48], 'little'), 0xAABBCCDD)

    def test_second_writer_is_rejected(self):
        with mock.patch.object(virtualcam, 'installed', return_value=True):
            camera = virtualcam.VirtualCamera(64, 48)
            self.addCleanup(camera.close)
            with self.assertRaises(ValueError):
                virtualcam.VirtualCamera(64, 48)

    def test_missing_obs_is_reported(self):
        with mock.patch.object(virtualcam, 'installed', return_value=False):
            with self.assertRaises(ValueError):
                virtualcam.VirtualCamera(64, 48)


if __name__ == '__main__':
    unittest.main()
