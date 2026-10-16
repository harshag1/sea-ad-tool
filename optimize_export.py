import json
from pathlib import Path
import resource
import subprocess
import sys
import time

import anndata as ad
from anndata.io import sparse_dataset
import h5py
import numpy as np
import pandas as pd

from sea_ad_slice import Catalog
from sea_ad_slice.core import read_frame_rows

root = Path(__file__).resolve().parent
print('Waiting for baseline source-validation assertions to finish', flush=True)
deadline = time.monotonic() + 1800
while True:
    log = (root / 'results/validation-pipeline.log').read_text()
    if 'SEAAD_VALIDATION_COMPLETE' in log and (root / 'results/benchmark.json').exists():
        break
    if 'Traceback' in log:
        raise RuntimeError('Baseline validation failed; inspect validation-pipeline.log')
    if time.monotonic() > deadline:
        raise TimeoutError('Baseline validation did not finish within the bounded wait')
    time.sleep(10)
results = json.loads((root / 'results/benchmark.json').read_text())
if not results.get('real_subset_verified') or not results.get('pseudobulk_donor_verified'):
    raise RuntimeError('Baseline scientific validation is incomplete')
catalog = Catalog(root / 'data/mtg.sqlite')
baseline_export = results['export'].copy()
canonical = root / 'results/immune_panel.h5ad'
optimized_path = root / 'results/immune_panel_compact.h5ad'
for preserved in ['immune_panel_baseline.h5ad', 'immune_pseudobulk_baseline.h5ad']:
    if (root / 'results' / preserved).exists():
        raise FileExistsError(f'Preserved baseline already exists: {preserved}')
print('Exporting with selected categorical levels only', flush=True)
optimized = catalog.export(optimized_path, filters=results['filters'], genes=baseline_export['requested_genes'], layer='UMIs', limit=5000, split_seed=42)
print('Optimized export seconds:', optimized['elapsed_seconds'], 'bytes:', optimized['output_bytes'], flush=True)
new = ad.read_h5ad(optimized_path)
with h5py.File(canonical, 'r') as handle:
    old_counts = sparse_dataset(handle['X'])[:, :].tocsr()
    assert (new.X != old_counts).nnz == 0
    old_obs = read_frame_rows(handle['obs'], np.arange(new.n_obs, dtype=np.int64))
    old_var = read_frame_rows(handle['var'], np.arange(new.n_vars, dtype=np.int64))
    old_barcode_levels = len(handle['obs/bc/categories'])
pd.testing.assert_frame_equal(new.obs.astype(object), old_obs.astype(object), check_dtype=False)
pd.testing.assert_frame_equal(new.var.astype(object), old_var.astype(object), check_dtype=False)
assert len(new.obs['bc'].cat.categories) == new.obs['bc'].nunique(dropna=True)
assert len(new.obs['bc'].cat.categories) <= new.n_obs
baseline_path = root / 'results/immune_panel_baseline.h5ad'
canonical.rename(baseline_path)
canonical.with_suffix('.h5ad.json').rename(baseline_path.with_suffix('.h5ad.json'))
optimized_path.rename(canonical)
optimized_path.with_suffix('.h5ad.json').unlink()
optimized['output'] = str(canonical)
canonical.with_suffix('.h5ad.json').write_text(json.dumps(optimized, indent=2))
baseline_export['output'] = str(baseline_path)
baseline_results = {**results, 'export': baseline_export}
(root / 'results/baseline-benchmark.json').write_text(json.dumps(baseline_results, indent=2))
print('Revalidating donor aggregation without a wide-table scan', flush=True)
bulk_path = root / 'results/immune_pseudobulk.h5ad'
old_bulk = ad.read_h5ad(bulk_path)
started = time.perf_counter()
bulk = catalog.pseudobulk(filters=results['filters'], genes=baseline_export['requested_genes'], layer='UMIs')
calculation_seconds = time.perf_counter() - started
assert (bulk.X != old_bulk.X).nnz == 0
pd.testing.assert_frame_equal(bulk.obs.astype(object), old_bulk.obs.astype(object), check_dtype=False)
pd.testing.assert_frame_equal(bulk.var.astype(object), old_bulk.var.astype(object), check_dtype=False)
bulk_path.rename(root / 'results/immune_pseudobulk_baseline.h5ad')
started = time.perf_counter()
bulk.write_h5ad(bulk_path)
write_seconds = time.perf_counter() - started
results['baseline_pseudobulk'] = results['pseudobulk'].copy()
results['pseudobulk'] = {'output': str(bulk_path), 'shape': list(bulk.shape), 'cells': int(bulk.obs['n_cells'].sum()), 'seconds': calculation_seconds + write_seconds}
results['optimized_pseudobulk_verified'] = True
results['export'] = optimized
results['baseline_export'] = baseline_export
results['metadata_optimization'] = {
    'source_barcode_levels': old_barcode_levels,
    'exported_barcode_levels': len(new.obs['bc'].cat.categories),
    'all_metadata_values_identical': True,
    'all_expression_values_identical': True,
    'file_size_reduction_ratio': baseline_export['output_bytes'] / optimized['output_bytes'],
    'observed_elapsed_ratio': baseline_export['elapsed_seconds'] / optimized['elapsed_seconds'],
    'timing_caveat': 'Before/after runs used different cache states; not a controlled algorithmic speedup estimate',
    'optimization_process_peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
}
results['source_to_export_byte_ratio'] = catalog.source.stat().st_size / canonical.stat().st_size
results['optimized_metadata_verified'] = True
(root / 'results/benchmark.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results['metadata_optimization'], indent=2), flush=True)
subprocess.run([sys.executable, '-u', str(root / 'make_report.py')], cwd=root, check=True)
print('SEAAD_OPTIMIZED_VALIDATION_COMPLETE', flush=True)
