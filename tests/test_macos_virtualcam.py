import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
import cv2  # Load once before patching sys.modules; native modules cannot be re-imported safely.
from engine import virtualcam


class MacCameraTests(unittest.TestCase):
    def setUp(self):
        self.bridge = SimpleNamespace(Camera=Mock(), PixelFormat=SimpleNamespace(BGR='BGR'))
        self.patches = [patch('platform.mac_ver', return_value=('14.0', '', 'arm64')),
                        patch.dict(sys.modules, pyvirtualcam=self.bridge)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_mac_dispatch_uses_obs_bgr_and_closes_once(self):
        with patch.object(virtualcam.sys, 'platform', 'darwin'):
            camera = virtualcam.open_camera(641, 481)
        self.bridge.Camera.assert_called_once_with(width=640, height=480, fps=30, fmt='BGR', backend='obs')
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = [10, 20, 30]
        camera.send(frame[:, ::-1])
        sent = self.bridge.Camera.return_value.send.call_args.args[0]
        self.assertTrue(sent.flags.c_contiguous)
        np.testing.assert_array_equal(sent[0, 0], [10, 20, 30])
        camera.close()
        camera.close()
        self.bridge.Camera.return_value.close.assert_called_once()
        with self.assertRaisesRegex(ValueError, 'kapalı'):
            camera.send(frame)

    def test_missing_obs_has_actionable_turkish_error(self):
        self.bridge.Camera.side_effect = RuntimeError('OBS camera missing')
        with self.assertRaisesRegex(ValueError, 'OBS Studio 30'):
            virtualcam.MacCamera(640, 480)

    def test_missing_python_bridge_has_actionable_error(self):
        with patch('importlib.import_module', side_effect=ImportError('missing')):
            with self.assertRaisesRegex(ValueError, 'bileşeni eksik'):
                virtualcam.MacCamera(640, 480)

    def test_unsupported_os_is_reported_before_opening_device(self):
        with patch('platform.mac_ver', return_value=('12.7', '', 'arm64')):
            with self.assertRaisesRegex(ValueError, 'macOS 13'):
                virtualcam.MacCamera(640, 480)
        self.bridge.Camera.assert_not_called()

    def test_resolution_is_normalized_before_send(self):
        camera = virtualcam.MacCamera(640, 480)
        camera.send(np.zeros((481, 641, 3), dtype=np.uint8))
        self.assertEqual(self.bridge.Camera.return_value.send.call_args.args[0].shape, (480, 640, 3))
        camera.close()

    def test_windows_routing_is_unchanged(self):
        with patch.object(virtualcam.sys, 'platform', 'win32'), patch.object(virtualcam, 'native_installed', return_value=True), patch.object(virtualcam, 'WindowsCamera') as native:
            virtualcam.open_camera(640, 480)
            native.assert_called_once_with()
