import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

import anndata as ad
from anndata.io import read_elem, write_elem
import h5py
import numpy as np
import pandas as pd
from scipy import sparse

from .kernel import filter_columns, integer_selection

VERSION = '0.1.2'


def quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def identity(path):
    path = Path(path).resolve()
    stat = path.stat()
    return {'path': str(path), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def matrix_info(handle, layer):
    key = 'X' if layer == 'X' else 'layers/' + layer
    if key not in handle:
        raise ValueError(f'Expression layer {layer!r} is unavailable')
    node = handle[key]
    encoding = node.attrs.get('encoding-type', '')
    if isinstance(encoding, bytes):
        encoding = encoding.decode()
    if encoding != 'csr_matrix':
        raise ValueError(f'{key} uses {encoding!r}; this bounded-row backend requires CSR')
    return node


def inspect_source(path):
    with h5py.File(path, 'r') as handle:
        matrices = {}
        for layer in ['X', *list(handle.get('layers', {}))]:
            key = 'X' if layer == 'X' else 'layers/' + layer
            node = handle[key]
            shape = node.attrs.get('shape', node.shape if isinstance(node, h5py.Dataset) else [])
            dtype = node['data'].dtype if isinstance(node, h5py.Group) and 'data' in node else getattr(node, 'dtype', 'unknown')
            matrices[layer] = {'encoding': str(node.attrs.get('encoding-type', 'dense')), 'shape': list(map(int, shape)), 'dtype': str(dtype)}
        return {'source': identity(path), 'matrices': matrices, 'obs_columns': [str(x) for x in handle['obs'].attrs['column-order']], 'var_columns': [str(x) for x in handle['var'].attrs['column-order']]}


def read_frame_rows(group, rows):
    rows = np.asarray(rows, dtype=np.int64)
    def take(dataset, selection=rows):
        selection = np.asarray(selection, dtype=np.int64)
        order = np.argsort(selection)
        sorted_rows = selection[order]
        inverse = np.argsort(order)
        if not len(selection):
            values = dataset[:0]
        elif len(selection) > dataset.shape[0] // 4:
            values = dataset[:][sorted_rows]
        else:
            pieces = [dataset[sorted_rows[start:start + 512]] for start in range(0, len(selection), 512)]
            values = np.concatenate(pieces) if pieces else dataset[:0]
        values = values[inverse]
        if values.dtype.kind in 'OSU':
            values = np.asarray([value.decode() if isinstance(value, bytes) else value for value in values], dtype=object)
        return values

    def element(node):
        if isinstance(node, h5py.Dataset):
            return take(node)
        encoding = node.attrs.get('encoding-type', '')
        if encoding == 'categorical':
            codes = take(node['codes'])
            present = codes >= 0
            used, inverse = np.unique(codes[present], return_inverse=True)
            remapped = np.full(len(codes), -1, dtype=np.int64)
            remapped[present] = inverse
            categories_node = node['categories']
            categories = take(categories_node, used) if isinstance(categories_node, h5py.Dataset) else read_elem(categories_node)[used]
            return pd.Categorical.from_codes(remapped, categories=categories, ordered=bool(node.attrs.get('ordered', False)))
        return read_elem(node)[rows]

    index_key = group.attrs['_index']
    frame = pd.DataFrame({name: element(group[name]) for name in group.attrs['column-order']}, index=pd.Index(element(group[index_key])))
    frame.index.name = None if index_key == '_index' else index_key
    return frame


def ensure_query_indexes(database):
    started = time.perf_counter()
    specifications = {
        'cohort_subclass_cover': ['Subclass', 'Neurotypical reference', 'Donor ID', '_row'],
        'cohort_supertype_cover': ['Supertype', 'Neurotypical reference', 'Donor ID', '_row'],
        'cohort_donor_cover': ['Donor ID', 'Subclass', 'Neurotypical reference', '_row'],
    }
    with sqlite3.connect(database, timeout=60) as connection:
        schema = json.loads(connection.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0])
        fields = set(schema['obs_columns']) | {'_row'}
        available = {row[1] for row in connection.execute('PRAGMA index_list(cells)')}
        created = []
        for name, columns in specifications.items():
            if name not in available and set(columns) <= fields:
                print(f'Building covering index: {name}', flush=True)
                connection.execute(f'CREATE INDEX {quote(name)} ON cells ({", ".join(quote(column) for column in columns)})')
                connection.execute(f'ANALYZE {quote(name)}')
                created.append(name)
        if created:
            schema['covering_indexes'] = sorted((set(schema.get('covering_indexes', [])) | set(created)))
            schema['query_index_seconds'] = time.perf_counter() - started
            connection.execute('UPDATE metadata SET value=? WHERE key=?', (json.dumps(schema), 'schema'))
    return {'created': created, 'seconds': time.perf_counter() - started}


def build_index(source, database, force=False):
    source = Path(source).resolve()
    database = Path(database).resolve()
    if database == source or database.with_suffix('.building.sqlite') == source:
        raise ValueError('Database paths must not replace the source')
    if database.exists() and not force:
        catalog = Catalog(database)
        if source != catalog.source:
            raise ValueError('Index belongs to a different source')
        catalog.check_source()
        ensure_query_indexes(database)
        return Catalog(database).summary()
    started = time.perf_counter()
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_suffix('.building.sqlite')
    if temporary.exists():
        temporary.unlink()
    schema = inspect_source(source)
    with h5py.File(source, 'r') as handle:
        obs = read_elem(handle['obs'])
        var = read_elem(handle['var'])
    if {'_row', '_cell_id'}.intersection(obs.columns) or {'_row', '_gene_id'}.intersection(var.columns):
        raise ValueError('Source metadata collides with reserved columns')
    if obs.index.has_duplicates:
        raise ValueError('Source cell IDs are not unique')
    schema.update(n_obs=len(obs), n_vars=len(var), index_version=VERSION)
    for info in schema['matrices'].values():
        if info['shape'] != [len(obs), len(var)]:
            raise ValueError('Expression and metadata shapes disagree')
    with sqlite3.connect(temporary) as connection:
        connection.execute('PRAGMA journal_mode=OFF')
        connection.execute('PRAGMA synchronous=OFF')
        connection.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute('INSERT INTO metadata VALUES (?, ?)', ('schema', json.dumps(schema)))
        frame = obs.copy(deep=False)
        frame.insert(0, '_row', np.arange(len(frame), dtype=np.int64))
        frame.insert(1, '_cell_id', obs.index.astype(str))
        frame.to_sql('cells', connection, index=False, chunksize=5000)
        connection.execute('CREATE UNIQUE INDEX row_idx ON cells (_row)')
        connection.execute('CREATE UNIQUE INDEX cell_id_idx ON cells (_cell_id)')
        indexed = []
        for number, column in enumerate(obs.columns):
            series = obs[column]
            if (isinstance(series.dtype, pd.CategoricalDtype) and series.nunique(dropna=False) <= 128) or str(column) in ['Donor ID', 'Subclass', 'Supertype', 'Class', 'Sex', 'Braak', 'Cognitive Status']:
                connection.execute(f'CREATE INDEX field_{number} ON cells ({quote(column)})')
                indexed.append(str(column))
        genes = var.copy()
        genes.insert(0, '_row', np.arange(len(var), dtype=np.int64))
        genes.insert(1, '_gene_id', var.index.astype(str))
        genes.to_sql('genes', connection, index=False, chunksize=5000)
        connection.execute('CREATE INDEX gene_id_idx ON genes (_gene_id)')
        schema.update(indexed_fields=indexed, build_seconds=time.perf_counter() - started)
        connection.execute('UPDATE metadata SET value=? WHERE key=?', (json.dumps(schema), 'schema'))
        connection.execute('ANALYZE')
    ensure_query_indexes(temporary)
    os.replace(temporary, database)
    return Catalog(database).summary()


class Catalog:
    def __init__(self, database):
        self.database = Path(database).resolve()
        if not self.database.is_file():
            raise FileNotFoundError(self.database)
        with self.connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = {'metadata', 'cells', 'genes'} - tables
            if missing:
                raise ValueError(f'Catalog is incomplete (missing {sorted(missing)}); rebuild with index --force')
            self.schema = json.loads(connection.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0])
        self.source = Path(self.schema['source']['path'])
        self.remote_source = None
        receipt_path = self.source.parent / 'download-receipt.json'
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt.get('bytes') == self.schema['source']['bytes'] and receipt.get('url', '').rsplit('/', 1)[-1] == self.source.name:
                self.remote_source = receipt
        self.fields = set(self.schema['obs_columns']) | {'_row', '_cell_id'}

    def connect(self):
        return sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True)

    def check_source(self):
        if identity(self.source) != self.schema['source']:
            raise ValueError('Source file identity changed; rebuild the index')

    def summary(self):
        return self.schema

    def predicate(self, filters):
        clauses, values = [], []
        for field, condition in (filters or {}).items():
            if field not in self.fields:
                raise ValueError(f'Unknown metadata field: {field}')
            column = quote(field)
            if isinstance(condition, dict):
                operations = {'gte': '>=', 'lte': '<=', 'gt': '>', 'lt': '<', 'eq': '=', 'ne': '!='}
                for operation, value in condition.items():
                    if operation not in operations or value is None:
                        raise ValueError('Unsupported comparison; use null equality for missing values')
                    clauses.append(f'{column} {operations[operation]} ?')
                    values.append(value)
            elif condition is None:
                clauses.append(f'{column} IS NULL')
            elif isinstance(condition, list):
                if not condition:
                    clauses.append('0')
                else:
                    if len(condition) > 500:
                        raise ValueError('At most 500 values per filter')
                    has_null = None in condition
                    nonnull = [v for v in condition if v is not None]
                    parts = []
                    if nonnull:
                        parts.append(f'{column} IN ({",".join("?" for _ in nonnull)})')
                        values.extend(nonnull)
                    if has_null:
                        parts.append(f'{column} IS NULL')
                    clauses.append('(' + ' OR '.join(parts) + ')')
            else:
                clauses.append(f'{column} = ?')
                values.append(condition)
        return (' AND '.join(clauses) if clauses else '1'), values

    def rows(self, filters=None, limit=None):
        if limit is not None and (not isinstance(limit, int) or limit < 0):
            raise ValueError('limit must be a nonnegative integer')
        where, values = self.predicate(filters)
        sql = f'SELECT _row FROM cells WHERE {where} ORDER BY _row'
        if limit is not None:
            sql += ' LIMIT ?'
            values.append(limit)
        with self.connect() as connection:
            return np.fromiter((row[0] for row in connection.execute(sql, values)), dtype=np.int64)

    def preview(self, filters=None, group_by='Donor ID'):
        if group_by not in self.fields:
            raise ValueError(f'Unknown grouping field: {group_by}')
        started = time.perf_counter()
        where, values = self.predicate(filters)
        with self.connect() as connection:
            count = connection.execute(f'SELECT COUNT(*) FROM cells WHERE {where}', values).fetchone()[0]
            groups = connection.execute(f'SELECT {quote(group_by)}, COUNT(*) FROM cells WHERE {where} GROUP BY {quote(group_by)} ORDER BY COUNT(*) DESC', values).fetchall()
        return {'cells': count, 'group_by': group_by, 'groups': [{'value': value, 'cells': number} for value, number in groups], 'query_seconds': time.perf_counter() - started}

    def genes(self, names=None):
        with self.connect() as connection:
            frame = pd.read_sql_query('SELECT * FROM genes ORDER BY _row', connection)
        if names is None:
            return frame['_row'].to_numpy(np.int64)
        if len(names) != len(set(names)):
            raise ValueError('Duplicate requested genes')
        lookup = {}
        for column in frame.columns:
            if column == '_row':
                continue
            for row, value in zip(frame['_row'], frame[column]):
                if isinstance(value, str):
                    lookup.setdefault(value, set()).add(int(row))
        result = []
        for name in names:
            matches = lookup.get(name, set())
            if len(matches) != 1:
                raise ValueError(f'Gene {name!r} is missing or ambiguous ({len(matches)} matches)')
            result.append(next(iter(matches)))
        if len(result) != len(set(result)):
            raise ValueError('Gene aliases resolve to duplicate source features')
        return np.asarray(result, dtype=np.int64)

    def batches(self, rows, columns, layer='X', batch_rows=2048, max_nnz=2000000, engine='rust'):
        self.check_source()
        rows = integer_selection(rows, self.schema['n_obs'], label='Rows')
        columns = integer_selection(columns, self.schema['n_vars'])
        if engine not in ['rust', 'scipy']:
            raise ValueError('Engine must be rust or scipy')
        if batch_rows < 1 or max_nnz < 1:
            raise ValueError('Batch limits must be positive')
        if len(rows) and (rows[0] < 0 or rows[-1] >= self.schema['n_obs'] or np.any(np.diff(rows) <= 0)):
            raise ValueError('Rows must be sorted, unique, and within source shape')
        with h5py.File(self.source, 'r', rdcc_nbytes=32 * 1024 * 1024) as handle:
            node = matrix_info(handle, layer)
            pointers = node['indptr'][:].astype(np.int64, copy=False)
            position = 0
            while position < len(rows):
                first = int(rows[position])
                stop = position + 1
                while stop < len(rows) and stop - position < batch_rows:
                    candidate = int(rows[stop])
                    if candidate - int(rows[stop - 1]) > 32 or candidate - first >= batch_rows or pointers[candidate + 1] - pointers[first] > max_nnz:
                        break
                    stop += 1
                last = int(rows[stop - 1]) + 1
                lower, upper = int(pointers[first]), int(pointers[last])
                block = sparse.csr_matrix((node['data'][lower:upper], node['indices'][lower:upper], pointers[first:last + 1] - lower), shape=(last - first, self.schema['n_vars']))
                selected = block[rows[position:stop] - first]
                yield rows[position:stop], filter_columns(selected, columns, engine=engine)
                position = stop

    def donor_values(self, rows, donor_field):
        if donor_field not in self.schema['obs_columns']:
            raise ValueError('Unknown donor field')
        self.check_source()
        with h5py.File(self.source, 'r') as handle:
            values = read_elem(handle['obs'][donor_field])
        return pd.Series(values[rows])

    def donor_splits(self, rows, donor_field='Donor ID', seed=0):
        if donor_field not in self.fields:
            raise ValueError('Unknown donor field')
        self.check_source()
        rows = integer_selection(rows, self.schema['n_obs'], label='Rows')
        selected = self.donor_values(rows, donor_field)
        if selected.isna().any():
            raise ValueError('Cannot split cells with missing donor identifiers')
        unique = sorted(set(selected.astype(str)))
        ordered = sorted(unique, key=lambda value: hashlib.sha256(f'{seed}:{value}'.encode()).hexdigest())
        if len(ordered) < 3:
            raise ValueError('At least three donors are needed for three nonempty splits')
        validation = max(1, int(round(len(ordered) * 0.1)))
        test = max(1, int(round(len(ordered) * 0.1)))
        assignments = {donor: ('validation' if i < validation else 'test' if i < validation + test else 'train') for i, donor in enumerate(ordered)}
        return np.asarray([assignments[str(value)] for value in selected], dtype=object), assignments

    def export(self, output, filters=None, genes=None, layer='X', limit=None, batch_rows=2048, engine='rust', split_seed=None, donor_field='Donor ID'):
        self.check_source()
        output = Path(output).resolve()
        if output.exists() or output == self.source or output == self.database:
            raise FileExistsError('Output must be a new path')
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + '.partial')
        if temporary.exists():
            raise FileExistsError(temporary)
        started = time.perf_counter()
        rows, columns = self.rows(filters, limit), self.genes(genes)
        recipe = {'tool_version': VERSION, 'source': self.schema['source'], 'remote_source': self.remote_source, 'source_release': self.source.name, 'filters': filters or {}, 'requested_genes': genes, 'source_gene_rows': columns.tolist(), 'layer': layer, 'limit': limit, 'engine': engine, 'split_seed': split_seed, 'donor_field': donor_field, 'qc_population': 'source-defined; inspect release metadata', 'semantics': 'Source values preserved without normalization; see source release documentation'}
        with h5py.File(self.source, 'r') as source_handle:
            node = matrix_info(source_handle, layer)
            dtype = node['data'].dtype
            obs = read_frame_rows(source_handle['obs'], rows)
            var = read_frame_rows(source_handle['var'], columns)
        obs['_source_row'] = rows
        var['_source_column'] = columns
        if split_seed is not None:
            splits, assignments = self.donor_splits(rows, donor_field, split_seed)
            obs['_split'] = pd.Categorical(splits, categories=['train', 'validation', 'test'])
            recipe['donor_splits'] = assignments
        recipe['recipe_id'] = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
        written = 0
        try:
            with h5py.File(temporary, 'w') as handle:
                handle.attrs.update({'encoding-type': 'anndata', 'encoding-version': '0.1.0'})
                write_elem(handle, 'obs', obs)
                write_elem(handle, 'var', var)
                for key in ['obsm', 'varm', 'obsp', 'varp', 'layers']:
                    write_elem(handle, key, {})
                write_elem(handle, 'uns', {'sea_ad_slice': json.dumps(recipe, sort_keys=True)})
                group = handle.create_group('X')
                group.attrs.update({'encoding-type': 'csr_matrix', 'encoding-version': '0.1.0', 'shape': np.array([len(rows), len(columns)], dtype=np.int64)})
                data = group.create_dataset('data', shape=(0,), maxshape=(None,), dtype=dtype, chunks=(65536,), compression='lzf')
                indices = group.create_dataset('indices', shape=(0,), maxshape=(None,), dtype=np.int64, chunks=(65536,), compression='lzf')
                pointers = group.create_dataset('indptr', shape=(len(rows) + 1,), dtype=np.int64)
                pointers[0] = 0
                out_row = 0
                for selected_rows, block in self.batches(rows, columns, layer, batch_rows, engine=engine):
                    end = written + block.nnz
                    data.resize((end,))
                    indices.resize((end,))
                    data[written:end] = block.data
                    indices[written:end] = block.indices
                    pointers[out_row + 1:out_row + len(selected_rows) + 1] = block.indptr[1:] + written
                    written = end
                    out_row += len(selected_rows)
            os.replace(temporary, output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        result = {**recipe, 'output': str(output), 'n_obs': len(rows), 'n_vars': len(columns), 'nnz': written, 'output_bytes': output.stat().st_size, 'elapsed_seconds': time.perf_counter() - started}
        output.with_suffix(output.suffix + '.json').write_text(json.dumps(result, indent=2))
        return result

    def pseudobulk(self, filters=None, genes=None, layer=None, donor_field='Donor ID', engine='rust'):
        if layer is None or layer == 'X':
            raise ValueError('Explicit raw-count layer is required; X is not assumed to be raw counts')
        rows, columns = self.rows(filters), self.genes(genes)
        if donor_field not in self.fields:
            raise ValueError('Unknown donor field')
        selected = self.donor_values(rows, donor_field)
        if selected.isna().any():
            raise ValueError('Missing donor identifiers')
        names = sorted(set(selected.astype(str)))
        codes = pd.Categorical(selected.astype(str), categories=names).codes
        accumulator = sparse.csr_matrix((len(names), len(columns)), dtype=np.int64)
        position = 0
        maximum_cells_per_donor = int(np.bincount(codes, minlength=len(names)).max(initial=0))
        for batch, matrix in self.batches(rows, columns, layer=layer, engine=engine):
            if matrix.data.size and (np.any(matrix.data < 0) or not np.all(np.isfinite(matrix.data)) or not np.all(matrix.data == np.floor(matrix.data))):
                raise ValueError('Selected layer contains invalid raw counts')
            if matrix.data.size and int(matrix.data.max()) > np.iinfo(np.int64).max // max(1, maximum_cells_per_donor):
                raise OverflowError('Count range is unsafe for int64 donor aggregation')
            matrix = matrix.astype(np.int64)
            group = sparse.csr_matrix((np.ones(len(batch), dtype=np.int64), (codes[position:position + len(batch)], np.arange(len(batch)))), shape=(len(names), len(batch)))
            accumulator = accumulator + group @ matrix
            position += len(batch)
        with h5py.File(self.source, 'r') as handle:
            var = read_elem(handle['var']).iloc[columns].copy()
        obs = pd.DataFrame({'n_cells': np.bincount(codes, minlength=len(names))}, index=pd.Index(names, name=donor_field))
        result = ad.AnnData(accumulator, obs=obs, var=var)
        result.uns['sea_ad_slice'] = json.dumps({'source': self.schema['source'], 'remote_source': self.remote_source, 'source_release': self.source.name, 'filters': filters or {}, 'layer': layer, 'aggregation': 'sum raw counts by donor', 'tool_version': VERSION})
        return result
