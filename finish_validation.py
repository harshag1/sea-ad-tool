import os
import json
from sea_ad_slice.core import ensure_query_indexes
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
started = time.monotonic()
deadline = started + 1800
print('Waiting for atomic publication of the existing metadata index; no second builder is started.', flush=True)
while not ((root / 'data/mtg.sqlite').exists() and (root / 'results/index-metrics.json').exists()):
    log = (root / 'results/index.log').read_text()
    if 'Traceback' in log or 'MemoryError' in log:
        raise RuntimeError('Metadata index failed; inspect results/index.log')
    if time.monotonic() > deadline:
        raise TimeoutError('Metadata index was not published within the 30-minute bounded validation wait')
    time.sleep(10)
print('INDEX_PUBLISHED: optimizing cohort query plans', flush=True)
optimization = ensure_query_indexes(root / 'data/mtg.sqlite')
metrics_path = root / 'results/index-metrics.json'
metrics = json.loads(metrics_path.read_text())
if optimization['created']:
    metrics['metadata_index_seconds'] = metrics['wall_seconds']
    metrics['query_index_seconds'] = optimization['seconds']
    metrics['wall_seconds'] += optimization['seconds']
    metrics['covering_indexes'] = optimization['created']
    metrics_path.write_text(json.dumps(metrics, indent=2))
print('QUERY_INDEXES_READY: starting real-data validation and benchmarks', flush=True)
environment = dict(os.environ)
environment['PYTHONPATH'] = str(root / 'src')
with (root / 'results/benchmark.log').open('w') as log:
    subprocess.run([sys.executable, '-u', str(root / 'benchmark.py')], cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
print('REAL_DATA_VALIDATION_PASSED', flush=True)
with (root / 'results/report-generation.log').open('w') as log:
    subprocess.run([sys.executable, str(root / 'make_report.py')], cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
print('SEAAD_VALIDATION_COMPLETE', flush=True)
