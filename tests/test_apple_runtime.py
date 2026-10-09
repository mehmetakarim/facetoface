import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from engine.apple_runtime import coreml_options, prepare_coreml_temp


class AppleRuntimeTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        disk = patch('engine.apple_runtime.shutil.disk_usage', return_value=SimpleNamespace(free=10 * 1024 ** 3))
        disk.start()
        self.addCleanup(disk.stop)

    def test_low_disk_space_is_reported_before_compilation(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'model.onnx'
            model.write_bytes(b'model')
            with patch.dict(os.environ, {'DLC_COREML_CACHE': str(Path(folder) / 'cache')}):
                with patch('engine.apple_runtime.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
                    with self.assertRaisesRegex(ValueError, '3 GB'):
                        coreml_options(model, '1.23.2')

    def test_cache_reused_and_invalidated(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'model.onnx'
            model.write_bytes(b'first')
            with patch.dict(os.environ, {'DLC_COREML_CACHE': str(Path(folder) / 'cache')}):
                first = coreml_options(model, '1.23.2')
                self.assertEqual(first, coreml_options(model, '1.23.2'))
                self.assertNotEqual(first, coreml_options(model, '1.23.3'))
                model.write_bytes(b'changed model')
                self.assertNotEqual(first, coreml_options(model, '1.23.2'))
                self.assertEqual(first['ModelFormat'], 'MLProgram')

    def test_old_runtime_rejected_before_loading_model(self):
        with self.assertRaisesRegex(ValueError, 'güncellemesi'):
            coreml_options('missing.onnx', '1.16.3')

    def test_scratch_in_disposable_job(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'DLC_JOB_DIR': folder}, clear=True), patch.object(tempfile, 'tempdir', None):
                prepare_coreml_temp()
                expected = str(Path(folder) / 'coreml')
                self.assertEqual(os.environ['TMPDIR'], expected)
                self.assertEqual(tempfile.gettempdir(), expected)
