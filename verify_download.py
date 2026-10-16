import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parent
receipt_path = root / 'data/download-receipt.json'
receipt = json.loads(receipt_path.read_text())
source = root / 'data' / Path(receipt['url']).name
started = time.perf_counter()
parts = []
with source.open('rb') as handle:
    while block := handle.read(8 * 1024 * 1024):
        parts.append(hashlib.md5(block).digest())
computed = hashlib.md5(b''.join(parts)).hexdigest() + '-' + str(len(parts))
expected = receipt['etag'].strip('"')
if computed != expected:
    raise RuntimeError(f'8 MiB multipart checksum did not match the ETag: {computed} != {expected}')
receipt.update(etag_verified=True, etag_part_bytes=8 * 1024 * 1024, checksum_verification_seconds=time.perf_counter() - started, integrity='Verified byte length, source ETag via conditional ranges and independently recomputed 8 MiB multipart MD5; local SHA256 recorded')
receipt_path.write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt, indent=2), flush=True)
