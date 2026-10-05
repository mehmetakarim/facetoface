"""Opt-in integration check using only the repository's demo media.
Run from the project root: venv/bin/python scripts/smoke_engine.py
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import threading
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ('venv/Scripts/python.exe' if os.name == 'nt' else 'venv/bin/python')

def worker(config, directory):
    started = time.monotonic()
    env = {**os.environ, 'NO_ALBUMENTATIONS_UPDATE': '1', 'DLC_DEBUG_STACKS': '1',
           'MPLCONFIGDIR': str(directory / 'mpl'), 'XDG_CACHE_HOME': str(directory / 'cache'),
           'DLC_JOB_DIR': str(directory)}
    with open(directory / f"{config['mode']}.log", 'w', encoding='utf-8') as log:
        process = subprocess.Popen([str(PYTHON), '-u', str(ROOT / 'engine/worker.py')],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                   text=True, encoding='utf-8', env=env, start_new_session=True)
        events = []
        def collect():
            for line in process.stdout:
                event = json.loads(line)
                if 'image' in event:
                    event['image'] = f"JPEG preview ({len(event['image'])} characters)"
                events.append(event)
                print(json.dumps(event, ensure_ascii=False), flush=True)
        reader = threading.Thread(target=collect, daemon=True)
        reader.start()
        process.stdin.write(json.dumps(config) + '\n')
        process.stdin.close()
        try:
            process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            print((directory / f"{config['mode']}.log").read_text(encoding='utf-8', errors='replace')[-3000:], flush=True)
            raise AssertionError('Motor 180 saniye içinde işlemi tamamlayamadı.')
        reader.join(timeout=5)
    assert process.returncode == 0, (directory / f"{config['mode']}.log").read_text(encoding='utf-8', errors='replace')[-3000:]
    assert any(e['type'] == 'complete' for e in events)
    assert events[-1]['type'] == 'finished'
    print(f"{config['mode']}: {time.monotonic() - started:.1f}s", flush=True)

with tempfile.TemporaryDirectory(prefix='yuz-smoke-') as temp:
    directory = Path(temp)
    demo = Image.open(ROOT / 'media/demo.gif').convert('RGB')
    source = directory / 'source.jpg'
    target = directory / 'target.jpg'
    demo.crop((78, 78, 138, 141)).resize((360, 378)).save(source)
    demo.crop((264, 67, 582, 249)).resize((636, 364)).save(target)
    image_out = directory / 'result.png'
    config = {'mode': 'image', 'source': str(source), 'target': str(target), 'output': str(image_out),
              'provider': 'directml' if '--directml' in sys.argv else 'cpu'}
    if '--video-only' not in sys.argv:
        worker(config, directory)
        assert Image.open(image_out).size == (636, 364)
        assert image_out.stat().st_size > 1000
    # A short video with audio checks frame count, encoding and audio restoration.
    video = directory / 'target.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-loop', '1', '-i', str(target), '-f', 'lavfi', '-i',
                    'sine=frequency=440:sample_rate=44100', '-t', '1', '-r', '3', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(video)], check=True, timeout=30)
    video_out = directory / 'result.mp4'
    worker({**config, 'mode': 'video', 'target': str(video), 'output': str(video_out)}, directory)
    metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video_out)]))
    streams = metadata['streams']
    assert any(s['codec_type'] == 'audio' for s in streams)
    stream = next(s for s in streams if s['codec_type'] == 'video')
    assert int(stream['nb_frames']) == 3, stream
    assert (stream['width'], stream['height']) == (636, 364)
    print('PASS: video, frame count, dimensions, audio and JSON protocol', flush=True)
