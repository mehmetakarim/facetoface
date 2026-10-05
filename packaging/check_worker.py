"""Run the frozen engine without the checkout or developer tools on PATH."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

worker = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='yuz paket testi ') as directory:
    env = {**os.environ, 'DLC_PROJECT_ROOT': directory,
           'PYTHONIOENCODING': 'cp1252', 'PYTHONPATH': ''}
    if sys.platform == 'win32':
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    result = subprocess.run([str(worker)], cwd=directory, env=env,
                            input=b'{"mode":"diagnostics","check_inference":true}\n',
                            capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    events = [json.loads(line) for line in result.stdout.decode('utf-8').splitlines()]
    diagnostics = next(event for event in events if event['type'] == 'diagnostics')
    assert diagnostics['ffmpeg'], diagnostics
    assert 'CPUExecutionProvider' in diagnostics['providers'], diagnostics
    if sys.platform == 'win32':
        assert 'DmlExecutionProvider' in diagnostics['providers'], diagnostics
    assert events[-1]['type'] == 'finished', events
    Path('diagnostics.jsonl').write_bytes(result.stdout)
    # Camera names must load without the checkout; CI runners have no cameras.
    listed = subprocess.run([str(worker)], cwd=directory, env=env, input=b'{"mode":"cameras"}
',
                            capture_output=True, timeout=60)
    if listed.returncode:
        raise RuntimeError(listed.stderr.decode('utf-8', errors='replace'))
    assert any(json.loads(line)['type'] == 'cameras' for line in listed.stdout.decode('utf-8').splitlines()), listed.stdout
    print('PASS: isolated packaged engine, UTF-8, inference imports, CPU/DirectML providers, bundled FFmpeg')
