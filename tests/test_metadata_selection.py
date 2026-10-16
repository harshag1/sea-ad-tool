import anndata as ad
import h5py
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from sea_ad_slice.core import read_frame_rows


@pytest.mark.parametrize('rows', [[0, 3], [3, 0], [], [2], [0, 1, 2, 3]])
def test_only_selected_categorical_levels_are_loaded(tmp_path, rows):
    categories = [f'barcode-{index:05d}' for index in range(10000)]
    obs = pd.DataFrame({'bc': pd.Categorical.from_codes([9999, 0, -1, 5000], categories=categories, ordered=True), 'numeric': [1., 2., 3., 4.]}, index=['c0', 'c1', 'c2', 'c3'])
    obj = ad.AnnData(sparse.csr_matrix(np.eye(4)), obs=obs)
    path = tmp_path / 'categories.h5ad'
    obj.write_h5ad(path)
    with h5py.File(path, 'r') as handle:
        selected = read_frame_rows(handle['obs'], np.asarray(rows, dtype=np.int64))
    expected = obs.iloc[rows]
    pd.testing.assert_frame_equal(selected.astype(object), expected.astype(object))
    assert selected['bc'].cat.ordered
    assert len(selected['bc'].cat.categories) == expected['bc'].nunique(dropna=True)
