import ctypes
from pathlib import Path

import numpy as np
from scipy import sparse

_LIBRARY = None


def integer_selection(values, size, unique=True, label='Selection'):
    array = np.asarray(values)
    if array.ndim != 1 or (array.size and array.dtype.kind not in 'iu'):
        raise ValueError(f'{label} must be a one-dimensional integer array')
    if array.size and (array.min() < 0 or array.max() >= size):
        raise ValueError(f'{label} is outside source shape')
    result = array.astype(np.int64, copy=False)
    if unique and len(np.unique(result)) != len(result):
        raise ValueError(f'{label} must be unique')
    return result


def filter_columns(matrix, columns, engine='rust'):
    matrix = sparse.csr_matrix(matrix)
    columns = integer_selection(columns, matrix.shape[1])
    if engine == 'scipy':
        return matrix[:, columns].tocsr()
    if engine != 'rust':
        raise ValueError('Engine must be rust or scipy')
    global _LIBRARY
    if _LIBRARY is None:
        path = Path(__file__).resolve().parents[2] / 'rust' / 'libsparse_filter.so'
        if not path.exists():
            raise RuntimeError('Compile the Rust kernel with the documented rustc command, or choose engine=scipy')
        _LIBRARY = ctypes.CDLL(str(path))
    types = {'float32': 'f32', 'float64': 'f64', 'int32': 'i32', 'int64': 'i64', 'uint32': 'u32', 'uint64': 'u64'}
    if matrix.data.dtype.name not in types:
        return matrix[:, columns].tocsr()
    pointers = np.require(matrix.indptr, dtype=np.int64, requirements=['C', 'A'])
    indices = np.require(matrix.indices, dtype=np.int64, requirements=['C', 'A'])
    values = np.require(matrix.data, dtype=matrix.data.dtype.newbyteorder('='), requirements=['C', 'A'])
    if pointers[0] != 0 or pointers[-1] != len(values) or np.any(pointers[1:] < pointers[:-1]) or len(indices) != len(values):
        raise ValueError('Malformed CSR buffers')
    mapping = np.full(matrix.shape[1], -1, dtype=np.int64)
    mapping[columns] = np.arange(len(columns), dtype=np.int64)
    output_pointers = np.empty(matrix.shape[0] + 1, dtype=np.int64)
    output_indices = np.empty(len(indices), dtype=np.int64)
    output_values = np.empty_like(values)
    function = getattr(_LIBRARY, 'filter_' + types[values.dtype.name])
    function.argtypes = [ctypes.c_size_t, ctypes.c_size_t] + [ctypes.c_void_p] * 7
    function.restype = ctypes.c_int64
    buffers = [pointers, indices, values, mapping, output_pointers, output_indices, output_values]
    count = function(matrix.shape[0], matrix.shape[1], *[a.ctypes.data for a in buffers])
    if count < 0:
        raise ValueError('Malformed CSR column index')
    result = sparse.csr_matrix((output_values[:count].copy(), output_indices[:count].copy(), output_pointers), shape=(matrix.shape[0], len(columns)))
    result.sort_indices()
    return result
