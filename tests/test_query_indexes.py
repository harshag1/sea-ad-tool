import sqlite3
import pytest

from sea_ad_slice.core import Catalog, build_index, ensure_query_indexes


def test_covering_indexes_are_queryable_and_idempotent(indexed):
    catalog, obj, counts, root = indexed
    obj.obs['Neurotypical reference'] = False
    obj.obs['Supertype'] = obj.obs['Subclass'].copy()
    source = root / 'cover.h5ad'
    database = root / 'cover.sqlite'
    obj.write_h5ad(source)
    result = build_index(source, database)
    assert set(result['covering_indexes']) == {'cohort_subclass_cover', 'cohort_supertype_cover', 'cohort_donor_cover'}
    assert ensure_query_indexes(database)['created'] == []
    refreshed = Catalog(database)
    assert refreshed.preview({'Subclass': 'A', 'Neurotypical reference': False})['cells'] == 5
    with sqlite3.connect(database) as connection:
        plan = connection.execute('EXPLAIN QUERY PLAN SELECT COUNT(*) FROM cells WHERE "Subclass"=? AND "Neurotypical reference"=?', ['A', False]).fetchall()
    assert any('COVERING INDEX cohort_subclass_cover' in row[-1] for row in plan)


def test_incomplete_catalog_fails_early(indexed):
    catalog, obj, counts, root = indexed
    with sqlite3.connect(catalog.database) as connection:
        connection.execute('DROP TABLE genes')
    with pytest.raises(ValueError, match='Catalog is incomplete'):
        Catalog(catalog.database)


def test_donor_splits_do_not_scan_the_wide_sql_metadata(indexed, monkeypatch):
    catalog, obj, counts, root = indexed
    def reject_sql():
        raise AssertionError('Donor labels should come from the compact source column')
    monkeypatch.setattr(catalog, 'connect', reject_sql)
    labels, assignments = catalog.donor_splits([0, 1, 2, 3, 4, 5, 6], seed=42)
    assert len(labels) == 7
    assert set(assignments) == {'d0', 'd1', 'd2', 'd3'}
