import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from engine import audio
from engine.worker import find_ffmpeg

FFMPEG = find_ffmpeg()


def first_loud_second(ffmpeg, path):
    """Time of the first sample above half scale in the file's audio."""
    raw = subprocess.run([ffmpeg, '-v', 'error', '-i', str(path), '-f', 's16le', '-ac', '1', '-ar', '8000', '-'],
                         capture_output=True, check=True).stdout
    samples = np.abs(np.frombuffer(raw, np.int16))
    return int(np.argmax(samples > 8000)) / 8000


@unittest.skipUnless(FFMPEG, 'FFmpeg is required')
class JoinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'video.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=64x48:r=30:d=3',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(self.video)], check=True)
        # One second of silence, then a loud tone: the tone marks "1 s after audio began".
        self.audio = self.root / 'audio.m4a'
        subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono:d=1',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:d=4',
                        '-filter_complex', '[0:a][1:a]concat=n=2:v=0:a=1,volume=8', '-c:a', 'aac', str(self.audio)],
                        check=True)

    def probe(self, path):
        return json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)],
                                         capture_output=True, text=True).stdout)['streams']

    def test_audio_that_started_early_is_trimmed(self):
        out = self.root / 'early.mp4'
        # Audio began at t=10.0, video at t=11.0: the tone must be heard right away.
        self.assertTrue(audio.join(FFMPEG, self.video, self.audio, 10.0, 11.0, out))
        self.assertEqual({s['codec_type'] for s in self.probe(out)}, {'video', 'audio'})
        self.assertLess(first_loud_second(FFMPEG, out), 0.15)

    def test_audio_that_started_late_is_delayed(self):
        out = self.root / 'late.mp4'
        # Audio began 0.5 s after the video: its tone (1 s in) lands at 1.5 s.
        self.assertTrue(audio.join(FFMPEG, self.video, self.audio, 10.5, 10.0, out))
        self.assertAlmostEqual(first_loud_second(FFMPEG, out), 1.5, delta=0.15)


class ListingTests(unittest.TestCase):
    def listing(self, platform, text):
        result = SimpleNamespace(stderr=text.encode('utf-8'))
        with mock.patch.object(audio.sys, 'platform', platform), mock.patch.object(audio.subprocess, 'run', return_value=result):
            return audio.list_microphones('ffmpeg')

    def test_windows_uses_the_stable_alternative_name(self):
        text = '''[dshow @ 0] "Integrated Camera" (video)
[dshow @ 0]   Alternative name "@device_pnp_camera"
[dshow @ 0] "Mikrofon Dizisi (Realtek(R) Audio)" (audio)
[dshow @ 0]   Alternative name "@device_cm_{33D9}\\wave_{23FF}"
'''
        self.assertEqual(self.listing('win32', text),
                         [{'id': '@device_cm_{33D9}\\wave_{23FF}', 'name': 'Mikrofon Dizisi (Realtek(R) Audio)'}])

    def test_macos_lists_audio_devices_by_index(self):
        text = '''[AVFoundation indev @ 0] AVFoundation video devices:
[AVFoundation indev @ 0] [0] FaceTime HD Camera
[AVFoundation indev @ 0] AVFoundation audio devices:
[AVFoundation indev @ 0] [0] MacBook Air Mikrofonu
[AVFoundation indev @ 0] [1] AirPods
'''
        self.assertEqual(self.listing('darwin', text),
                         [{'id': '0', 'name': 'MacBook Air Mikrofonu'}, {'id': '1', 'name': 'AirPods'}])

    def test_no_ffmpeg_means_no_microphones(self):
        self.assertEqual(audio.list_microphones(None), [])


if __name__ == '__main__':
    unittest.main()
