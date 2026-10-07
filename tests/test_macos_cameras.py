import unittest
from unittest.mock import patch
from engine.cameras import indexed_inputs, resolve_mac_camera


class MacCameraTests(unittest.TestCase):
    def test_output_filtered_without_renumbering(self):
        self.assertEqual(indexed_inputs([('B', 'FaceTime'), ('A', 'OBS Virtual Camera')]),
                         [{'index': 1, 'id': 'B', 'name': 'FaceTime'}])

    @patch('engine.cameras.mac_cameras', return_value=[{'index': 2, 'id': 'B', 'name': 'FaceTime'}])
    def test_stable_id_survives_reordering(self, _):
        self.assertEqual(resolve_mac_camera(1, 'B'), 2)

    @patch('engine.cameras.mac_cameras', return_value=[{'index': 1, 'id': 'B', 'name': 'FaceTime'}])
    def test_old_output_index_rejected(self, _):
        with self.assertRaises(ValueError):
            resolve_mac_camera(0)
        with self.assertRaises(ValueError):
            resolve_mac_camera(1, 'disconnected')


class CameraPermissionTests(unittest.TestCase):
    def av(self, status, granted=True):
        from types import SimpleNamespace
        return SimpleNamespace(
            AVMediaTypeVideo='video', AVAuthorizationStatusAuthorized=3,
            AVAuthorizationStatusNotDetermined=0,
            AVCaptureDevice=SimpleNamespace(
                authorizationStatusForMediaType_=lambda _: status,
                requestAccessForMediaType_completionHandler_=lambda _, callback: callback(granted)))

    def test_authorized_and_new_grant(self):
        from engine.cameras import ensure_mac_camera_permission
        for status in (0, 3):
            with patch.dict('sys.modules', {'AVFoundation': self.av(status)}):
                ensure_mac_camera_permission()

    def test_denied_existing_or_requested(self):
        from engine.cameras import ensure_mac_camera_permission
        for status in (0, 2):
            with patch.dict('sys.modules', {'AVFoundation': self.av(status, False)}):
                with self.assertRaises(ValueError):
                    ensure_mac_camera_permission()
