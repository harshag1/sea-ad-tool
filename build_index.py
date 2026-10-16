import json
from pathlib import Path
import resource
import time

from sea_ad_slice import build_index

root = Path(__file__).resolve().parent
started = time.perf_counter()
print('Building full MTG metadata index', flush=True)
result = build_index(root / 'data/SEAAD_MTG_RNAseq_final-nuclei.2026-06-22.h5ad', root / 'data/mtg.sqlite')
result['wall_seconds'] = time.perf_counter() - started
result['peak_rss_mb'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
(root / 'results/index-metrics.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2), flush=True)
