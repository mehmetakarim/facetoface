import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from engine.output import publish

class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'sonuç.png'
        self.env = patch.dict(os.environ, {'DLC_JOB_DIR': str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_existing_result_is_never_replaced(self):
        self.output.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            publish(self.output, data=b'new')
        self.assertEqual(self.output.read_bytes(), b'original')
        self.assertEqual(list(self.root.iterdir()), [self.output])

    def test_failed_copy_leaves_no_partial_output(self):
        with self.assertRaises(FileNotFoundError):
            publish(self.output, source=self.root / 'missing')
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_successful_result_is_complete(self):
        data = b'complete result' * 1000
        publish(self.output, data=data)
        self.assertEqual(self.output.read_bytes(), data)
        self.assertEqual(list(self.root.iterdir()), [self.output])
