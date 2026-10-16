import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request

root = Path(__file__).resolve().parent / 'data'
source = json.loads((root / 'source.json').read_text())
target = root / Path(source['url']).name
partial = target.with_suffix('.h5ad.part')
state_path = root / 'download-state.json'
chunk_size = 64 * 1024 * 1024
lock = threading.Lock()
started = time.monotonic()
if target.exists():
    if target.stat().st_size != source['bytes']:
        raise RuntimeError('Existing target has the wrong size')
    print('Download already complete', flush=True)
    raise SystemExit(0)
if state_path.exists():
    state = json.loads(state_path.read_text())
    if state['source'] != source or state['chunk_size'] != chunk_size:
        raise RuntimeError('Resume identity mismatch')
    if not partial.exists():
        raise RuntimeError('Resume state exists without partial file')
else:
    state = {'source': source, 'chunk_size': chunk_size, 'completed': []}
fd = os.open(partial, os.O_RDWR | os.O_CREAT, 0o644)
os.ftruncate(fd, source['bytes'])
completed = set(state['completed'])
initial = len(completed)
count = (source['bytes'] + chunk_size - 1) // chunk_size

def fetch(index):
    start = index * chunk_size
    end = min(start + chunk_size, source['bytes']) - 1
    for attempt in range(6):
        try:
            request = urllib.request.Request(source['url'], headers={'Range': f'bytes={start}-{end}', 'If-Match': source['etag']})
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{source["bytes"]}':
                    raise RuntimeError('Server did not honor the exact requested range')
                if response.headers.get('ETag') != source['etag']:
                    raise RuntimeError('Remote object changed')
                position = start
                while block := response.read(1024 * 1024):
                    if position + len(block) > end + 1:
                        raise RuntimeError('Oversized range response')
                    view = memoryview(block)
                    while view:
                        written = os.pwrite(fd, view, position)
                        position += written
                        view = view[written:]
                if position != end + 1:
                    raise RuntimeError('Truncated range response')
            with lock:
                os.fsync(fd)
                completed.add(index)
                state['completed'] = sorted(completed)
                temporary = state_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(state))
                temporary.replace(state_path)
                if len(completed) % 8 == 0 or len(completed) == count:
                    elapsed = time.monotonic() - started
                    rate = (len(completed) - initial) * chunk_size / max(elapsed, 0.001) / 1e6
                    print(f'chunks: {len(completed)}/{count}, downloaded_gb: {min(len(completed)*chunk_size,source["bytes"])/1e9:.3f}, MB_per_s: {rate:.1f}', flush=True)
            return
        except Exception:
            if attempt == 5:
                raise
            time.sleep(min(2 ** attempt, 20))

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(fetch, [i for i in range(count) if i not in completed]))
os.fsync(fd)
os.close(fd)
digest = hashlib.sha256()
with partial.open('rb') as stream:
    while block := stream.read(16 * 1024 * 1024):
        digest.update(block)
receipt = {**source, 'sha256': digest.hexdigest(), 'download_seconds': time.monotonic() - started, 'integrity': 'Exact conditional HTTP ranges and byte length; local SHA256 recorded, not compared to publisher SHA256'}
partial.replace(target)
(root / 'download-receipt.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt), flush=True)
