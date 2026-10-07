import json
import tempfile
import unittest
from pathlib import Path
from engine.protocol import validate, encode

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'kaynak.jpg'
        self.target = self.root / 'hedef.jpg'
        self.source.write_bytes(b'test')
        self.target.write_bytes(b'test')
        self.config = dict(mode='image', source=str(self.source), target=str(self.target), output=str(self.root / 'sonuc.png'))
    def test_original_files_cannot_be_overwritten(self):
        for path in [self.source, self.target]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate({**self.config, 'output': str(path)})
    def test_existing_output_is_preserved(self):
        path = self.root / 'sonuc.png'
        path.write_bytes(b'keep')
        with self.assertRaises(ValueError): validate(self.config)
        self.assertEqual(path.read_bytes(), b'keep')
    def test_valid_image_job(self):
        self.assertEqual(validate(self.config), self.config)
    def test_providers(self):
        for provider in ['cpu', 'coreml', 'directml']:
            with self.subTest(provider=provider):
                self.assertEqual(validate({**self.config, 'provider': provider})['provider'], provider)
        with self.assertRaises(ValueError): validate({**self.config, 'provider': 'cuda'})
    def test_occlusion_flag(self):
        self.assertTrue(validate({**self.config, 'occlusion': False}) is not None)
        with self.assertRaises(ValueError): validate({**self.config, 'occlusion': 'yes'})
    def test_live_camera_validation(self):
        for camera in [-1, 10, '0', True]:
            with self.subTest(camera=camera), self.assertRaises(ValueError):
                validate(dict(mode='live', source=str(self.source), camera=camera))
    def test_camera_id_validation(self):
        for device_id in ['', 3, True, 'x' * 1025]:
            with self.subTest(device_id=device_id), self.assertRaises(ValueError):
                validate(dict(mode='live', source=str(self.source), camera_id=device_id))
        self.assertEqual(validate(dict(mode='live', source=str(self.source), camera_id='B'))['camera_id'], 'B')
    def test_wrong_output_format(self):
        with self.assertRaises(ValueError): validate({**self.config, 'output': str(self.root / 'bad.mp4')})
    def test_protocol_keeps_turkish_and_single_line(self):
        event = {'message': 'Yüz hazır.\nİşlem başlıyor.'}
        encoded = encode(event)
        self.assertEqual(encoded.count('\n'), 1)
        self.assertEqual(json.loads(encoded), event)
    def test_missing_source_and_unknown_mode(self):
        self.assertEqual(validate({'mode': 'cameras'}), {'mode': 'cameras'})
        for config in [{'mode':'unknown'}, {'mode':'source','source':'missing.jpg'}]:
            with self.assertRaises(ValueError): validate(config)

if __name__ == '__main__': unittest.main()
