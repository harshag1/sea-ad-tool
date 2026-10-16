import json
from pathlib import Path
import resource
import statistics
import time

import anndata as ad
from anndata.io import read_elem, sparse_dataset
import h5py
import numpy as np
from scipy import sparse

from sea_ad_slice import Catalog
from sea_ad_slice.kernel import filter_columns

root = Path(__file__).resolve().parent
catalog = Catalog(root / 'data/mtg.sqlite')
results = {'source': catalog.schema['source'], 'shape': [catalog.schema['n_obs'], catalog.schema['n_vars']], 'cache_policy': 'Existing OS cache; no cache eviction. Not a cold benchmark.', 'measurements': {}}
with catalog.connect() as connection:
    subclasses = connection.execute('SELECT Subclass, COUNT(*) FROM cells GROUP BY Subclass ORDER BY COUNT(*) DESC').fetchall()
    donors = connection.execute('SELECT COUNT(DISTINCT "Donor ID") FROM cells').fetchone()[0]
results.update(donors=donors, subclasses=subclasses)
chosen = next((name for name, number in subclasses if name and ('microglia' in name.lower() or 'immune' in name.lower())), subclasses[-1][0])
filters = {'Subclass': chosen, 'Neurotypical reference': False}
results['filters'] = filters
where, bindings = catalog.predicate(filters)
with catalog.connect() as connection:
    results['query_plans'] = {
        'count': connection.execute('EXPLAIN QUERY PLAN SELECT COUNT(*) FROM cells WHERE ' + where, bindings).fetchall(),
        'donors': connection.execute('EXPLAIN QUERY PLAN SELECT "Donor ID",COUNT(*) FROM cells WHERE ' + where + ' GROUP BY "Donor ID"', bindings).fetchall(),
    }
panel = ['APOE', 'TREM2', 'TYROBP', 'P2RY12', 'SST', 'MAPT']
columns = catalog.genes(panel)
preview_times = []
for _ in range(10):
    preview = catalog.preview(filters)
    preview_times.append(preview['query_seconds'])
    print(f"Preview trial {len(preview_times)}/10: {preview['query_seconds']:.4f} seconds", flush=True)
results['preview'] = preview
results['measurements']['preview_p50_seconds'] = statistics.median(preview_times)
results['measurements']['preview_p95_seconds'] = float(np.percentile(preview_times, 95))
print('Preview', results['measurements'], flush=True)
output = root / 'results/immune_panel.h5ad'
if output.exists():
    output.unlink()
export = catalog.export(output, filters=filters, genes=panel, layer='UMIs', limit=5000, split_seed=42)
results['export'] = export
print('Export', json.dumps(export), flush=True)
restored = ad.read_h5ad(output)
rows = catalog.rows(filters, limit=5000)
with h5py.File(catalog.source, 'r') as handle:
    started = time.perf_counter()
    reference = sparse_dataset(handle['layers/UMIs'])[rows, :][:, columns].tocsr()
    results['measurements']['reference_backed_matrix_read_seconds'] = time.perf_counter() - started
    assert (reference != restored.X).nnz == 0
    source_cell_ids = handle['obs'][handle['obs'].attrs['_index']].asstr()[rows.tolist()]
    np.testing.assert_array_equal(restored.obs_names, source_cell_ids)
    np.testing.assert_array_equal(restored.var_names, read_elem(handle['var']).index[columns])
    source_block = sparse_dataset(handle['layers/UMIs'])[rows[:1000], :].tocsr()
    full_gene_columns = np.arange(catalog.schema['n_vars'], dtype=np.int64)
    normalized_blocks = [block for _, block in catalog.batches(rows[:64], full_gene_columns, layer='X')]
    normalized = sparse.vstack(normalized_blocks, format='csr')
    normalized_reference = sparse_dataset(handle['X'])[rows[:64], :].tocsr()
    assert (normalized != normalized_reference).nnz == 0
    results['normalized_all_gene_subset_verified'] = True
for engine in ['scipy', 'rust']:
    durations = []
    for _ in range(5):
        started = time.perf_counter()
        filtered = filter_columns(source_block, columns, engine)
        durations.append(time.perf_counter() - started)
    assert (filtered != reference[:1000]).nnz == 0
    results['measurements'][f'{engine}_filter_p50_seconds'] = statistics.median(durations)
for donor, cells in restored.obs.groupby('Donor ID', observed=True):
    assert cells['_split'].nunique() == 1
results['real_subset_verified'] = True
bulk_path = root / 'results/immune_pseudobulk.h5ad'
started = time.perf_counter()
bulk = catalog.pseudobulk(filters=filters, genes=panel, layer='UMIs')
bulk.write_h5ad(bulk_path)
results['pseudobulk'] = {'output': str(bulk_path), 'shape': list(bulk.shape), 'cells': int(bulk.obs['n_cells'].sum()), 'seconds': time.perf_counter() - started}
with h5py.File(catalog.source, 'r') as handle:
    donor_rows = catalog.rows({**filters, 'Donor ID': str(bulk.obs_names[0])})
    check = sparse_dataset(handle['layers/UMIs'])[donor_rows, :][:, columns].sum(axis=0)
    np.testing.assert_array_equal(np.asarray(check), bulk.X[0].toarray())
results['pseudobulk_donor_verified'] = True
results['peak_rss_mb'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
results['source_to_export_byte_ratio'] = catalog.source.stat().st_size / output.stat().st_size
(root / 'results/benchmark.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2), flush=True)
