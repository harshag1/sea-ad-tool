import json
from pathlib import Path
import sqlite3
import time

from anndata.io import read_elem
import h5py
import numpy as np

from types import SimpleNamespace
from sea_ad_slice.core import identity

root = Path(__file__).resolve().parent
database = root / 'data/mtg.sqlite'
with sqlite3.connect(database) as connection:
    schema = json.loads(connection.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0])
catalog = SimpleNamespace(database=database, source=Path(schema['source']['path']), schema=schema)
if identity(catalog.source) != schema['source']:
    raise ValueError('Source identity changed; refusing catalog repair')
started = time.perf_counter()
with h5py.File(catalog.source, 'r') as handle:
    var = read_elem(handle['var'])
    sample_rows = np.linspace(0, catalog.schema['n_obs'] - 1, 64, dtype=np.int64)
    source_ids = handle['obs'][handle['obs'].attrs['_index']].asstr()[sample_rows.tolist()]
with sqlite3.connect(catalog.database, timeout=60) as connection:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    nrows, distinct_rows, first, last = connection.execute('SELECT COUNT(*),COUNT(DISTINCT _row),MIN(_row),MAX(_row) FROM cells').fetchone()
    if (nrows, distinct_rows, first, last) != (catalog.schema['n_obs'], catalog.schema['n_obs'], 0, catalog.schema['n_obs'] - 1):
        raise RuntimeError('Cell row inventory does not match source shape')
    bindings = ','.join('?' for _ in sample_rows)
    records = connection.execute(f'SELECT _row,_cell_id FROM cells WHERE _row IN ({bindings}) ORDER BY _row', sample_rows.tolist()).fetchall()
    np.testing.assert_array_equal([row[1] for row in records], source_ids)
    if 'genes' not in tables:
        genes = var.copy()
        genes.insert(0, '_row', np.arange(len(var), dtype=np.int64))
        genes.insert(1, '_gene_id', var.index.astype(str))
        genes.to_sql('genes', connection, index=False, chunksize=5000)
        connection.execute('CREATE INDEX gene_id_idx ON genes (_gene_id)')
    else:
        if connection.execute('SELECT COUNT(*) FROM genes').fetchone()[0] != len(var):
            raise RuntimeError('Existing gene table has an incorrect row count')
    schema = catalog.schema.copy()
    indexes = connection.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    schema['covering_indexes'] = [row[0] for row in indexes if row[0].startswith('cohort_')]
    schema['catalog_repaired'] = True
    connection.execute('UPDATE metadata SET value=? WHERE key=?', (json.dumps(schema), 'schema'))
    connection.execute('ANALYZE genes')
receipt = {'cells': nrows, 'genes': len(var), 'cell_ids_spot_checked': len(sample_rows), 'covering_indexes': schema['covering_indexes'], 'repair_seconds': time.perf_counter() - started}
(root / 'results/catalog-repair.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt, indent=2), flush=True)
