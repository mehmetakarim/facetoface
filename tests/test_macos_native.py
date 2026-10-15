import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from engine import macos_native, virtualcam


class NativeMacTests(unittest.TestCase):
    def test_bgra_frame_contract_and_letterbox(self):
        pixels = np.zeros((100, 200, 3), dtype=np.uint8)
        pixels[:] = [10, 20, 30]
        result = np.frombuffer(macos_native.encode_frame(pixels[:, ::-1]), dtype=np.uint8).reshape(480, 640, 4)
        np.testing.assert_array_equal(result[240, 320], [10, 20, 30, 255])
        np.testing.assert_array_equal(result[0, 0], [0, 0, 0, 255])

    def test_native_preferred_without_obs(self):
        with patch.object(virtualcam.sys, 'platform', 'darwin'), \
             patch.object(macos_native, 'installed', return_value=True), \
             patch.object(macos_native, 'MacNativeCamera') as native, \
             patch.object(virtualcam, 'MacCamera') as obs:
            virtualcam.open_camera(640, 480)
            native.assert_called_once_with(640, 480)
            obs.assert_not_called()

    def test_status_timeout_is_not_installed(self):
        import subprocess
        with patch.object(macos_native.sys, 'platform', 'darwin'), \
             patch.object(macos_native, 'helper_path', return_value='/tmp/helper'), \
             patch.object(macos_native.subprocess, 'run', side_effect=subprocess.TimeoutExpired('helper', 5)):
            self.assertFalse(macos_native.installed())

    def make_writer(self):
        writer = macos_native.MacNativeCamera.__new__(macos_native.MacNativeCamera)
        writer.condition = threading.Condition()
        writer.closed = False
        writer.failed = False
        writer.pending = None
        writer.thread = None
        writer.process = Mock()
        writer.process.poll.return_value = None
        return writer

    def test_pending_frame_is_replaced_not_queued(self):
        writer = self.make_writer()
        with patch.object(macos_native, 'encode_frame', side_effect=[b'old', b'new']):
            writer.send(None); writer.send(None)
        self.assertEqual(writer.pending, b'new')
        writer.close(); writer.close()
        writer.process.terminate.assert_called_once()

    def test_partial_pipe_writes_preserve_frame_boundary(self):
        writer = self.make_writer(); writer.pending = b'12345678'; received = bytearray()
        def write(data):
            chunk = bytes(data[:3]); received.extend(chunk)
            if len(received) == 8: writer.closed = True
            return len(chunk)
        writer.process.stdin.write.side_effect = write
        writer._write()
        self.assertEqual(received, b'12345678')

    def test_broken_pipe_is_reported_on_next_frame(self):
        writer = self.make_writer(); writer.pending = b'frame'
        writer.process.stdin.write.side_effect = BrokenPipeError()
        writer._write()
        self.assertTrue(writer.failed)
        with patch.object(macos_native, 'encode_frame', return_value=b'next'):
            with self.assertRaisesRegex(ValueError, 'aktarımı durdu'):
                writer.send(None)
        writer.close()
