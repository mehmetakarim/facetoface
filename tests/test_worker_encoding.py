"""The engine wire format must remain UTF-8 on non-Turkish Windows systems."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class WorkerEncodingTests(unittest.TestCase):
    def test_turkish_errors_use_utf8_even_with_legacy_console_encoding(self):
        worker = Path(__file__).resolve().parents[1] / 'engine' / 'worker.py'
        result = subprocess.run(
            [sys.executable, str(worker)],
            input=json.dumps({'mode': 'geçersiz'}, ensure_ascii=False).encode('utf-8') + b'\n',
            capture_output=True,
            env={**os.environ, 'PYTHONIOENCODING': 'cp1252'},
            timeout=15,
        )
        self.assertEqual(result.returncode, 1)
        event = json.loads(result.stdout.decode('utf-8'))
        self.assertEqual(event['type'], 'error')
        self.assertEqual(event['message'], 'Geçersiz çalışma modu.')
