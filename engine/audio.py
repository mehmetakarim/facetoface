"""Record the microphone next to a live recording and join it to the video.

FFmpeg captures the device (DirectShow on Windows, AVFoundation on macOS) into
AAC while the engine writes the video. Opening a microphone takes a moment, so
the moment of the first recorded sample is estimated from FFmpeg's progress
reports on the engine's clock; the join then shifts the audio onto the video.
"""
import re
import subprocess
import sys
import threading
import time

FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}


def list_microphones(ffmpeg):
    """[{'id', 'name'}]: id is what FFmpeg opens, name is what people see."""
    if not ffmpeg or sys.platform not in ('win32', 'darwin'):
        return []
    if sys.platform == 'win32':
        command = [ffmpeg, '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy']
    else:
        command = [ffmpeg, '-hide_banner', '-f', 'avfoundation', '-list_devices', 'true', '-i', '']
    try:
        listing = subprocess.run(command, capture_output=True, timeout=15, **FLAGS).stderr.decode('utf-8', 'replace')
    except (OSError, subprocess.TimeoutExpired):
        return []
    microphones = []
    if sys.platform == 'win32':
        name = None
        for line in listing.splitlines():
            found = re.search(r'"(.+)" \(audio\)', line)
            if found:
                name = found.group(1)
                continue
            alternative = re.search(r'Alternative name "(.+)"', line)
            if name and alternative:
                # The alternative name is stable and ASCII, unlike localised display names.
                microphones.append({'id': alternative.group(1), 'name': name})
                name = None
    else:
        audio = False
        for line in listing.splitlines():
            if 'AVFoundation audio devices' in line:
                audio = True
            elif audio:
                found = re.search(r'\[(\d+)\] (.+)$', line)
                if found:
                    microphones.append({'id': found.group(1), 'name': found.group(2).strip()})
    return microphones


def _input(device):
    if sys.platform == 'win32':
        # A small buffer keeps capture latency low and the start estimate accurate.
        return ['-f', 'dshow', '-audio_buffer_size', '50', '-i', f'audio={device}']
    return ['-f', 'avfoundation', '-i', f':{device}']


class Microphone:
    def __init__(self, ffmpeg, device, path):
        self.path = path
        self.started = None  # engine clock time of the first recorded sample
        self.process = subprocess.Popen(
            [ffmpeg, '-hide_banner', '-nostats', '-loglevel', 'error', *_input(device),
             '-c:a', 'aac', '-b:a', '160k', '-progress', 'pipe:1', '-stats_period', '0.1', '-y', str(path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **FLAGS)
        threading.Thread(target=self._progress, daemon=True).start()

    def _progress(self):
        for line in self.process.stdout:
            found = re.match(rb'out_time_us=(\d+)', line)
            if found and int(found.group(1)) > 0:
                # Reports arrive a little late; the earliest estimate is the closest.
                start = time.monotonic() - int(found.group(1)) / 1e6
                self.started = start if self.started is None else min(self.started, start)

    def failed(self):
        return self.process.poll() is not None and self.started is None

    def stop(self):
        """Finish the file; True when it holds usable audio."""
        if self.process.poll() is None:
            try:
                self.process.stdin.write(b'q')  # FFmpeg's own graceful stop
                self.process.stdin.flush()
            except OSError:
                pass
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        return self.started is not None and self.path.is_file() and self.path.stat().st_size > 0

    def kill(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


def join(ffmpeg, video, audio, audio_start, video_start, output):
    """Mux with the audio moved so both start together; False if FFmpeg fails."""
    offset = video_start - audio_start
    if offset >= 0:
        # Audio began first: skip its head and keep the stream as recorded.
        seek, codec = ['-ss', f'{offset:.3f}'], ['-c:a', 'copy']
    else:
        # Audio began late: prepend real silence. A timestamp offset alone is
        # ignored by some players, which would play the sound too early.
        seek, codec = [], ['-af', f'adelay={round(-offset * 1000)}:all=1', '-c:a', 'aac', '-b:a', '160k']
    completed = subprocess.run(
        [ffmpeg, '-v', 'error', '-n', '-i', str(video), *seek, '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
         '-c:v', 'copy', *codec, '-shortest', '-movflags', '+faststart', str(output)],
        timeout=120, **FLAGS)
    return completed.returncode == 0
