# SEA-AD Slice implementation results

The complete selected MTG final-QC RNA release is downloaded and available through a local indexed cohort-query and sparse-export tool.

## Dataset and integrity

- Original file: `SEAAD_MTG_RNAseq_final-nuclei.2026-06-22.h5ad`.
- Download: 32,978,570,763 bytes in 750.5 seconds.
- Matrix: 1,178,694 nuclei × 36,601 genes; 84 distinct donor IDs.
- Source URL: https://sea-ad-single-cell-profiling.s3.amazonaws.com/MTG/RNAseq/SEAAD_MTG_RNAseq_final-nuclei.2026-06-22.h5ad.
- SHA256: `e06000cb8fc83ebad88a52a0a7c772747c38fa92c97debcfe4f59de7cea60c79`.
- Independently verified publisher multipart ETag: True.

## Measured results

| Measurement | Observed |
|---|---:|
| One-time metadata index build | 1689.3 s |
| Index build peak process RSS | 4446.3 MiB |
| Separate optimization attempt, ended unsuccessfully before exports | 633.3 s |
| Gene-catalog repair and row-identity checks | 12.41 s |
| Cohort preview median, 10 trials | 0.0585 s |
| Cohort preview p95, 10 trials | 0.0692 s |
| Sparse panel export | 47.754 s |
| Exported matrix shape | 5,000 × 6 |
| Export size, including metadata | 4,615,032 bytes |
| Baseline validation process peak RSS | 815.9 MiB |
| SciPy in-memory filter median | 0.005092 s |
| Rust in-memory filter median | 0.008342 s |
| Complete selected-class donor pseudobulk | 242.992 s |

Predicate: `{"Neurotypical reference": false, "Subclass": "Immune"}`. Panel: APOE, TREM2, TYROBP, P2RY12, SST, MAPT. The cell export uses the first 5,000 matching source rows as a bounded validation workload, not a representative sample.

## Selective metadata and donor lookup

The source barcode field carries 1,033,197 categorical labels. The optimized export retains only its 4,996 used labels; every cell annotation and expression value matches the independently source-validated baseline.

- Export size: 54.21 MB before, 4.62 MB after; 11.7× smaller.
- Observed export times: 350.35 s before, 47.75 s after.
- Donor labels now come from the compact source column, avoiding a full wide-table SQL scan. All donor aggregates match the source-validated baseline; observed pseudobulk times were 270.44 s before and 242.99 s after.
- Final optimization/validation process peak RSS: 329.8 MiB. Its checks differ from the baseline process, so these are not paired memory measurements.
- Cache states differed. These wall times are not a controlled algorithmic speedup estimate; the byte reduction and value equality are directly verified.

## Verification and interpretation

The exported counts exactly match an independent AnnData backed sparse read, with matching cell/gene order. A normalized-expression subset is additionally verified across all 36,601 genes. Selected donors have disjoint training splits. One donor's pseudobulk is checked against a direct source sum. Synthetic test results are in `tests-final.log`.

These are local measurements with existing filesystem caches, not controlled cold-cache or remote-service benchmarks. Reference backed read time excludes metadata and output writing, so it is not directly comparable to end-to-end export time. Rust/SciPy medians use the same already-loaded block.

The original-to-export file-size ratio is 7145.9× for this output, not a measured time or network speedup. The initial complete download is still required. Sparse batches avoid full matrix materialization; row pointers, selected IDs, and output metadata still consume memory.

## Scope and use

Implemented: local CSR slicing, indexed metadata, exact gene resolution, h5ad export/provenance, donor-disjoint splits, and donor count aggregation. Not implemented: hosted queries, gene-first matrix indexes, cross-release harmonization, biological label inference, or a graphical interface. Immune is not synonymous with pure microglia. Atlas associations are not causal perturbation labels.

See `../README.md` for CLI/notebook examples and `benchmark.json` for exact measurements. Source is in `../src/sea_ad_slice`; the Rust kernel is in `../rust/sparse_filter.rs`.

## Catalog recovery

The optimization attempt ended before exports with an incomplete catalog: cells and covering indexes were present, but the gene table was absent. The small gene table was rebuilt from the verified source in 12.41 seconds; all cell row IDs were checked for complete unique coverage, and 64 sampled cell identifiers matched the source. The cause was not established. The API now rejects incomplete catalogs early, and the final integrated suite passes 119 tests.

## Review execution note

Parallel reviewers returned `WorkerDeadlineExceededError: worker execution exceeded its 898.987s remaining deadline` and `WorkerDeadlineExceededError: worker execution exceeded its 898.897s remaining deadline`. Persisted tests and partial findings were inspected, boundary issues were fixed, and integrated tests were run directly; no completed independent final audit is claimed.
