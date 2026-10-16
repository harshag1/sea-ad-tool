import json
import os

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from sea_ad_slice.core import Catalog, build_index
from sea_ad_slice.kernel import filter_columns


def test_build_reuse_and_source_identity(indexed):
    catalog, obj, counts, root = indexed
    summary = build_index(catalog.source, catalog.database)
    assert summary['n_obs'] == 8
    assert summary['n_vars'] == 5
    assert summary['matrices']['counts']['encoding'] == 'csr_matrix'
    assert 'Donor ID' in summary['indexed_fields']
    assert summary == Catalog(catalog.database).summary()
    alternate = root / 'alternate.h5ad'
    obj.write_h5ad(alternate)
    with pytest.raises(ValueError, match='different source'):
        build_index(alternate, catalog.database)


@pytest.mark.parametrize('axis,column', [('obs', '_row'), ('obs', '_cell_id'), ('var', '_row'), ('var', '_gene_id')])
def test_reserved_metadata_rejected(indexed, axis, column):
    catalog, obj, counts, root = indexed
    getattr(obj, axis)[column] = 'collision'
    source = root / 'reserved.h5ad'
    obj.write_h5ad(source)
    with pytest.raises(ValueError, match='reserved'):
        build_index(source, root / 'reserved.sqlite')


def test_duplicate_cells_rejected(indexed):
    catalog, obj, counts, root = indexed
    obj.obs_names = ['same'] * obj.n_obs
    source = root / 'duplicates.h5ad'
    obj.write_h5ad(source)
    with pytest.raises(ValueError, match='not unique'):
        build_index(source, root / 'duplicates.sqlite')


@pytest.mark.parametrize('filters,expected', [(None, list(range(8))), ({}, list(range(8))), ({'Subclass': []}, []), ({'Donor ID': None}, [7]), ({'Donor ID': ['d1', None]}, [2, 3, 7]), ({'age': {'gte': 60, 'lt': 80}, 'Subclass': 'A'}, [2, 4]), ({'odd"field': "x' OR 1=1 --"}, [1]), ({'_cell_id': 'cell3'}, [3]), ({'_row': {'ne': 2}}, [0, 1, 3, 4, 5, 6, 7])])
def test_rows_filters(indexed, filters, expected):
    np.testing.assert_array_equal(indexed[0].rows(filters), expected)


@pytest.mark.parametrize('filters', [{'missing': 'x'}, {'age': {'like': 'x'}}, {'age': {'eq': None}}, {'Donor ID': ['x'] * 501}, {'age; DROP TABLE cells': 1}])
def test_invalid_filters_rejected(indexed, filters):
    with pytest.raises(ValueError):
        indexed[0].rows(filters)
    assert len(indexed[0].rows()) == 8


@pytest.mark.parametrize('limit', [-1, 1.5, '3'])
def test_invalid_limits(indexed, limit):
    with pytest.raises(ValueError, match='limit'):
        indexed[0].rows(limit=limit)


def test_limits_and_preview(indexed):
    catalog = indexed[0]
    np.testing.assert_array_equal(catalog.rows(limit=0), [])
    np.testing.assert_array_equal(catalog.rows(limit=2), [0, 1])
    result = catalog.preview({'Subclass': 'A'})
    assert result['cells'] == 5
    assert sum(group['cells'] for group in result['groups']) == 5
    assert {group['value'] for group in result['groups']} == {'d0', 'd1', 'd2', 'd3', None}
    assert catalog.preview({'Subclass': []})['groups'] == []
    with pytest.raises(ValueError, match='grouping'):
        catalog.preview(group_by='unknown')


def test_genes_alias_order_and_empty(indexed):
    catalog = indexed[0]
    np.testing.assert_array_equal(catalog.genes(), np.arange(5))
    np.testing.assert_array_equal(catalog.genes([]), [])
    np.testing.assert_array_equal(catalog.genes(['G4', 'ENSG0', 'a3']), [4, 0, 3])


@pytest.mark.parametrize('names,match', [(['missing'], '0 matches'), (['DUP'], '2 matches'), (['G0', 'G0'], 'Duplicate requested'), (['G0', 'ENSG0'], 'duplicate source')])
def test_invalid_genes(indexed, names, match):
    with pytest.raises(ValueError, match=match):
        indexed[0].genes(names)


@pytest.mark.parametrize('engine', ['rust', 'scipy'])
@pytest.mark.parametrize('layer', ['X', 'counts'])
def test_batches_values_order_and_bounds(indexed, engine, layer):
    catalog, obj, counts, root = indexed
    rows = np.array([0, 2, 3, 6])
    columns = np.array([4, 0, 3])
    batches = list(catalog.batches(rows, columns, layer=layer, batch_rows=2, max_nnz=5, engine=engine))
    np.testing.assert_array_equal(np.concatenate([item[0] for item in batches]), rows)
    actual = sparse.vstack([item[1] for item in batches]).toarray()
    expected = (obj.X if layer == 'X' else obj.layers[layer])[rows][:, columns].toarray()
    np.testing.assert_array_equal(actual, expected)
    assert all(len(batch_rows) <= 2 for batch_rows, block in batches)
    assert list(catalog.batches([], columns, engine=engine)) == []
    zero = list(catalog.batches(rows, [], engine=engine))
    assert all(block.shape[1] == 0 and block.nnz == 0 for batch_rows, block in zero)


@pytest.mark.parametrize('rows', [[-1], [8], [2, 1], [1, 1]])
def test_invalid_batch_rows(indexed, rows):
    with pytest.raises(ValueError, match='Rows'):
        list(indexed[0].batches(rows, [0]))


@pytest.mark.parametrize('kwargs', [{'batch_rows': 0}, {'max_nnz': 0}, {'layer': 'absent'}, {'engine': 'not-an-engine'}])
def test_invalid_batch_options(indexed, kwargs):
    with pytest.raises(ValueError):
        list(indexed[0].batches([0], [0], **kwargs))


@pytest.mark.parametrize('dtype', ['float32', 'float64', 'int32', 'int64', 'uint32', 'uint64', 'int16', 'bool'])
@pytest.mark.parametrize('shape', [(11, 9), (0, 9), (3, 0)])
def test_kernel_differential(dtype, shape):
    rng = np.random.default_rng(142)
    dense = rng.integers(0, 20, shape)
    dense[rng.random(shape) < 0.65] = 0
    matrix = sparse.csr_matrix(dense.astype(dtype))
    for columns in [list(reversed(range(shape[1]))), [], list(range(0, shape[1], 2))]:
        actual = filter_columns(matrix, columns, engine='rust')
        expected = filter_columns(matrix, columns, engine='scipy')
        np.testing.assert_array_equal(actual.toarray(), expected.toarray())
        assert actual.dtype == matrix.dtype
        assert actual.shape == expected.shape


def test_unsorted_duplicate_entries_kernel():
    matrix = sparse.csr_matrix((np.array([2., 3., 4., 5.]), np.array([3, 1, 3, 0]), np.array([0, 3, 4])), shape=(2, 4))
    actual = filter_columns(matrix, [3, 1])
    expected = filter_columns(matrix, [3, 1], engine='scipy')
    np.testing.assert_array_equal(actual.toarray(), expected.toarray())


@pytest.mark.parametrize('columns', [[1, 1], [-1], [3], [[0]]])
def test_invalid_kernel_columns(columns):
    with pytest.raises(ValueError):
        filter_columns(sparse.eye(3, format='csr'), columns)


def test_kernel_malformed_column_rejected():
    matrix = sparse.csr_matrix(([1.], [0], [0, 1]), shape=(1, 2))
    matrix.indices[0] = 3
    with pytest.raises(ValueError, match='Malformed CSR column'):
        filter_columns(matrix, [0])


@pytest.mark.parametrize('engine', ['rust', 'scipy'])
@pytest.mark.parametrize('filters,genes,limit', [({'Subclass': 'A'}, ['G4', 'ENSG0'], None), ({'Subclass': []}, None, None), (None, [], None), (None, None, 0)])
def test_export_roundtrip(indexed, engine, filters, genes, limit):
    catalog, obj, counts, root = indexed
    output = root / 'export.h5ad'
    result = catalog.export(output, filters=filters, genes=genes, layer='counts', limit=limit, engine=engine, batch_rows=2)
    restored = ad.read_h5ad(output)
    rows, columns = catalog.rows(filters, limit), catalog.genes(genes)
    np.testing.assert_array_equal(restored.X.toarray(), counts[np.ix_(rows, columns)])
    np.testing.assert_array_equal(restored.obs_names, obj.obs_names[rows])
    np.testing.assert_array_equal(restored.var_names, obj.var_names[columns])
    np.testing.assert_array_equal(restored.obs['_source_row'], rows)
    np.testing.assert_array_equal(restored.var['_source_column'], columns)
    assert restored.X.dtype == counts.dtype
    assert result['nnz'] == restored.X.nnz
    assert json.loads(restored.uns['sea_ad_slice'])['recipe_id'] == result['recipe_id']
    assert json.loads(output.with_suffix('.h5ad.json').read_text())['n_obs'] == len(rows)
    assert not (root / 'export.h5ad.partial').exists()
    with pytest.raises(FileExistsError):
        catalog.export(output)


def test_export_failure_cleanup(indexed):
    catalog, obj, counts, root = indexed
    output = root / 'failed.h5ad'
    with pytest.raises(ValueError):
        catalog.export(output, engine='bad')
    assert not output.exists()
    assert not (root / 'failed.h5ad.partial').exists()
    assert not output.with_suffix('.h5ad.json').exists()
    with pytest.raises(FileExistsError):
        catalog.export(catalog.source)
    with pytest.raises(FileExistsError):
        catalog.export(catalog.database)


def test_donor_splits_no_leakage(indexed):
    catalog, obj, counts, root = indexed
    rows = catalog.rows({'Donor ID': {'ne': 'unused'}})
    labels, assignments = catalog.donor_splits(rows, seed=17)
    repeated, repeated_assignments = catalog.donor_splits(rows, seed=17)
    np.testing.assert_array_equal(labels, repeated)
    assert assignments == repeated_assignments
    assert set(labels) == {'train', 'validation', 'test'}
    donors = obj.obs.iloc[rows]['Donor ID'].astype(str)
    for donor in donors.unique():
        assert len(set(labels[donors.to_numpy() == donor])) == 1
    output = root / 'split.h5ad'
    catalog.export(output, filters={'Donor ID': {'ne': 'unused'}}, split_seed=17)
    restored = ad.read_h5ad(output)
    np.testing.assert_array_equal(restored.obs['_split'].astype(str), labels)


@pytest.mark.parametrize('rows,field,match', [([0, 1], 'Donor ID', 'three'), ([7], 'Donor ID', 'missing'), ([], 'Donor ID', 'three'), ([0], 'absent', 'Unknown donor')])
def test_invalid_donor_splits(indexed, rows, field, match):
    with pytest.raises(ValueError, match=match):
        indexed[0].donor_splits(rows, donor_field=field)


@pytest.mark.parametrize('engine', ['rust', 'scipy'])
def test_pseudobulk_sum_and_empty(indexed, engine):
    catalog, obj, counts, root = indexed
    filters = {'Donor ID': {'ne': 'unused'}}
    bulk = catalog.pseudobulk(filters, genes=['G4', 'G0'], layer='counts', engine=engine)
    expected = np.vstack([counts[[0, 1]].sum(0), counts[[2, 3]].sum(0), counts[[4, 5]].sum(0), counts[[6]].sum(0)])[:, [4, 0]]
    np.testing.assert_array_equal(bulk.X.toarray(), expected)
    assert list(bulk.obs_names) == ['d0', 'd1', 'd2', 'd3']
    np.testing.assert_array_equal(bulk.obs['n_cells'], [2, 2, 2, 1])
    assert bulk.X.dtype == np.int64
    assert catalog.pseudobulk({'Subclass': []}, layer='counts').shape == (0, 5)
    assert catalog.pseudobulk(filters, genes=[], layer='counts').shape == (4, 0)


@pytest.mark.parametrize('layer,filters,match', [(None, {}, 'Explicit'), ('X', {}, 'Explicit'), ('counts', {}, 'Missing donor'), ('absent', {'Donor ID': 'd0'}, 'unavailable'), ('invalid', {'Donor ID': 'd0'}, 'invalid raw counts')])
def test_invalid_pseudobulk(indexed, layer, filters, match):
    with pytest.raises(ValueError, match=match):
        indexed[0].pseudobulk(filters=filters, layer=layer)


def test_stale_source_rejected(indexed):
    catalog, obj, counts, root = indexed
    stat = catalog.source.stat()
    os.utime(catalog.source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
    for action in [catalog.check_source, lambda: build_index(catalog.source, catalog.database), lambda: list(catalog.batches([0], [0])), lambda: catalog.export(root / 'stale.h5ad'), lambda: catalog.pseudobulk({'Donor ID': 'd0'}, layer='counts')]:
        with pytest.raises(ValueError, match='identity changed'):
            action()
    assert not (root / 'stale.h5ad').exists()
    assert build_index(catalog.source, catalog.database, force=True)['source']['mtime_ns'] == catalog.source.stat().st_mtime_ns


def test_build_index_refuses_to_replace_source(indexed):
    catalog, obj, counts, root = indexed
    source = root / 'must-preserve.h5ad'
    obj.write_h5ad(source)
    original = source.read_bytes()
    with pytest.raises((ValueError, FileExistsError)):
        build_index(source, source, force=True)
    assert source.read_bytes() == original


@pytest.mark.parametrize('rows', [[-2, 0, 2, 4], [0.5, 2, 4, 6]])
def test_donor_splits_reject_invalid_source_rows(indexed, rows):
    with pytest.raises(ValueError):
        indexed[0].donor_splits(rows)


def test_batches_reject_fractional_rows(indexed):
    with pytest.raises(ValueError):
        list(indexed[0].batches([0.5, 2.5], [0]))


@pytest.mark.parametrize('columns', [[-1], [5], [1, 1]])
def test_empty_batches_still_validate_columns(indexed, columns):
    with pytest.raises(ValueError):
        list(indexed[0].batches([], columns))


def test_pseudobulk_rejects_int64_sum_overflow(tmp_path):
    obs = pd.DataFrame({'Donor ID': ['d0', 'd0']}, index=['c0', 'c1'])
    obj = ad.AnnData(sparse.csr_matrix(np.array([[np.iinfo(np.int64).max], [1]], dtype=np.int64)), obs=obs)
    obj.layers['counts'] = obj.X.copy()
    source = tmp_path / 'overflow.h5ad'
    database = tmp_path / 'overflow.sqlite'
    obj.write_h5ad(source)
    build_index(source, database)
    with pytest.raises((ValueError, OverflowError)):
        Catalog(database).pseudobulk(layer='counts')


@pytest.mark.parametrize('bad_count', [-1.0, 0.5, float('nan'), float('inf')])
def test_pseudobulk_rejects_noncounts(tmp_path, bad_count):
    obs = pd.DataFrame({'Donor ID': ['d0']}, index=['c0'])
    obj = ad.AnnData(sparse.csr_matrix(np.array([[bad_count]])), obs=obs)
    obj.layers['counts'] = obj.X.copy()
    source = tmp_path / 'noncounts.h5ad'
    database = tmp_path / 'noncounts.sqlite'
    obj.write_h5ad(source)
    build_index(source, database)
    with pytest.raises(ValueError, match='invalid raw counts'):
        Catalog(database).pseudobulk(layer='counts')
