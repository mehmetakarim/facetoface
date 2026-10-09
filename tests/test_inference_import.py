"""Run explicitly with DLC_RUN_INFERENCE_TESTS=1 to check the native dependency boundary."""
import os
import subprocess
import sys
import unittest

@unittest.skipUnless(os.environ.get('DLC_RUN_INFERENCE_TESTS') == '1', 'Native import check is opt-in')
class InferenceImportTests(unittest.TestCase):
    def test_optional_renderers_are_not_imported(self):
        code = '''
import sys
from engine.inference import load_inference
get_model, Face = load_inference()
assert callable(get_model)
import tempfile
from pathlib import Path
from unittest.mock import patch
sentinel = object()
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'model.onnx'
    path.write_bytes(b'test')
    with patch.object(sys.modules['engine._insightface_inference.model_zoo.model_zoo'], 'ModelRouter') as router:
        get_model(str(path), sess_options=sentinel, providers=['CPUExecutionProvider'])
        router.return_value.get_model.assert_called_once_with(sess_options=sentinel, providers=['CPUExecutionProvider'])
assert Face(bbox=[1, 2, 3, 4]).bbox == [1, 2, 3, 4]
assert 'matplotlib.pyplot' not in sys.modules
assert 'tkinter' not in sys.modules
assert 'insightface' not in sys.modules
assert not any('mask_renderer' in name for name in sys.modules)
'''
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
