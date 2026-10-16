import numpy as np
import pytest
from scipy import sparse

from sea_ad_slice.kernel import filter_columns


@pytest.mark.parametrize('dtype', ['>f8', '>f4', '>i8', '>i4'])
def test_foreign_kernel_normalizes_endianness(dtype):
    matrix = sparse.csr_matrix(np.array([[1, 0, 3], [0, 4, 2]], dtype=np.float64))
    matrix.data = matrix.data.astype(dtype)
    actual = filter_columns(matrix, [2, 0], engine='rust')
    expected = filter_columns(matrix, [2, 0], engine='scipy')
    np.testing.assert_array_equal(actual.toarray(), expected.toarray())


def test_foreign_kernel_aligns_values():
    buffer = bytearray(33)
    values = np.ndarray((4,), dtype=np.float64, buffer=buffer, offset=1)
    values[:] = [1, 3, 4, 2]
    matrix = sparse.csr_matrix(([1., 3., 4., 2.], [0, 2, 1, 2], [0, 2, 4]), shape=(2, 3))
    matrix.data = values
    assert not matrix.data.flags.aligned
    np.testing.assert_array_equal(filter_columns(matrix, [2, 0]).toarray(), [[3, 1], [2, 0]])


def test_foreign_kernel_rejects_fractional_genes():
    with pytest.raises(ValueError):
        filter_columns(sparse.eye(3, format='csr'), [1.5])
