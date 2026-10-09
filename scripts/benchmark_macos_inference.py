"""Opt-in synthetic model benchmark; never opens a camera or saves user images."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--provider', choices=['cpu', 'coreml'], default='coreml')
parser.add_argument('--model', type=Path, default=ROOT / 'models' / 'inswapper_128.onnx')
parser.add_argument('--runs', type=int, default=3)
args = parser.parse_args()
if not 1 <= args.runs <= 100:
    parser.error('--runs must be between 1 and 100')
if args.provider == 'coreml':
    from engine.apple_runtime import prepare_coreml_temp, coreml_options
    prepare_coreml_temp()
import numpy as np
import onnxruntime as ort
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
options.log_severity_level = 3
providers = ['CPUExecutionProvider']
if args.provider == 'coreml':
    if 'CoreMLExecutionProvider' not in ort.get_available_providers():
        raise SystemExit('CoreML bu ortamda kullanılamıyor.')
    providers.insert(0, ('CoreMLExecutionProvider', coreml_options(args.model, ort.__version__)))
print(json.dumps({'runtime': ort.__version__, 'provider': args.provider}), flush=True)
start = time.monotonic()
session = ort.InferenceSession(str(args.model.resolve()), options, providers=providers)
print(json.dumps({'load_seconds': time.monotonic() - start}), flush=True)
rng = np.random.default_rng(1)
inputs = {'target': rng.random((1, 3, 128, 128), dtype=np.float32),
          'source': rng.random((1, 512), dtype=np.float32)}
inputs['source'] /= np.linalg.norm(inputs['source'])
timings = []
for index in range(args.runs + 1):
    start = time.monotonic()
    output = session.run(None, inputs)[0]
    elapsed = time.monotonic() - start
    if not np.isfinite(output).all():
        raise RuntimeError('Model geçersiz sayısal çıktı üretti.')
    if index:
        timings.append(elapsed)
    print(json.dumps({'warmup': index == 0, 'seconds': elapsed}), flush=True)
print(json.dumps({'median_seconds': statistics.median(timings)}), flush=True)
