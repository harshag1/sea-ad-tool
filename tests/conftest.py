import subprocess
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from sea_ad_slice.core import Catalog, build_index


@pytest.fixture(scope='session', autouse=True)
def rust_kernel():
    root = Path(__file__).resolve().parents[1]
    library = root / 'rust' / 'libsparse_filter.so'
    if not library.exists():
        subprocess.run(['rustc', '--crate-type', 'cdylib', '-O', str(root / 'rust' / 'sparse_filter.rs'), '-o', str(library)], check=True, timeout=60)
    return library


@pytest.fixture
def indexed(tmp_path):
    counts = np.array([[1, 0, 2, 0, 3], [0, 4, 0, 0, 0], [5, 0, 0, 6, 0], [0, 7, 8, 0, 0], [9, 0, 0, 0, 10], [0, 0, 11, 12, 0], [13, 0, 0, 0, 0], [0, 14, 0, 15, 16]], dtype=np.int64)
    obs = pd.DataFrame({'Donor ID': pd.Categorical(['d0', 'd0', 'd1', 'd1', 'd2', 'd2', 'd3', None]), 'Subclass': pd.Categorical(['A', 'B', 'A', 'B', 'A', 'B', 'A', 'A']), 'age': [50.0, 50.0, 60.0, 60.0, 70.0, 70.0, 80.0, np.nan], 'odd"field': ['safe', "x' OR 1=1 --", 'safe', 'safe', 'safe', 'safe', 'safe', 'safe']}, index=[f'cell{i}' for i in range(8)])
    var = pd.DataFrame({'gene_symbol': ['G0', 'DUP', 'DUP', 'G3', 'G4'], 'alias': ['a0', 'a1', 'a2', 'a3', 'a4']}, index=[f'ENSG{i}' for i in range(5)])
    obj = ad.AnnData(sparse.csr_matrix(counts.astype(np.float32) / 2), obs=obs, var=var)
    obj.layers['counts'] = sparse.csr_matrix(counts)
    obj.layers['invalid'] = sparse.csr_matrix(counts.astype(np.float64) - np.eye(8, 5) * 0.5)
    source = tmp_path / 'synthetic.h5ad'
    database = tmp_path / 'index.sqlite'
    obj.write_h5ad(source)
    build_index(source, database)
    return Catalog(database), obj, counts, tmp_path
