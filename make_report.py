import json
from pathlib import Path
import zipfile
import re

root = Path(__file__).resolve().parent
benchmark = json.loads((root / 'results/benchmark.json').read_text())
index = json.loads((root / 'results/index-metrics.json').read_text())
receipt = json.loads((root / 'data/download-receipt.json').read_text())
repair = json.loads((root / 'results/catalog-repair.json').read_text())
recovery = json.loads((root / 'results/recovery-note.json').read_text())
export = benchmark['export']
m = benchmark['measurements']
test_log = (root / 'results/tests-final.log').read_text()
if re.search(r'\d+ failed', test_log):
    raise RuntimeError('The integrated test suite has failures')
test_count = int(re.findall(r'(\d+) passed', test_log)[-1])
optimization_section = ''
if 'metadata_optimization' in benchmark:
    optimization = benchmark['metadata_optimization']
    before = benchmark['baseline_export']
    optimization_section = f'''## Selective metadata and donor lookup

The source barcode field carries {optimization['source_barcode_levels']:,} categorical labels. The optimized export retains only its {optimization['exported_barcode_levels']:,} used labels; every cell annotation and expression value matches the independently source-validated baseline.

- Export size: {before['output_bytes']/1e6:.2f} MB before, {export['output_bytes']/1e6:.2f} MB after; {optimization['file_size_reduction_ratio']:.1f}× smaller.
- Observed export times: {before['elapsed_seconds']:.2f} s before, {export['elapsed_seconds']:.2f} s after.
- Donor labels now come from the compact source column, avoiding a full wide-table SQL scan. All donor aggregates match the source-validated baseline; observed pseudobulk times were {benchmark['baseline_pseudobulk']['seconds']:.2f} s before and {benchmark['pseudobulk']['seconds']:.2f} s after.
- Final optimization/validation process peak RSS: {optimization['optimization_process_peak_rss_mb']:.1f} MiB. Its checks differ from the baseline process, so these are not paired memory measurements.
- Cache states differed. These wall times are not a controlled algorithmic speedup estimate; the byte reduction and value equality are directly verified.

'''
report = f'''# SEA-AD Slice implementation results

The complete selected MTG final-QC RNA release is downloaded and available through a local indexed cohort-query and sparse-export tool.

## Dataset and integrity

- Original file: `{Path(receipt['url']).name}`.
- Download: {receipt['bytes']:,} bytes in {receipt['download_seconds']:.1f} seconds.
- Matrix: {benchmark['shape'][0]:,} nuclei × {benchmark['shape'][1]:,} genes; {benchmark['donors']} distinct donor IDs.
- Source URL: {receipt['url']}.
- SHA256: `{receipt['sha256']}`.
- Independently verified publisher multipart ETag: {receipt.get('etag_verified', False)}.

## Measured results

| Measurement | Observed |
|---|---:|
| One-time metadata index build | {index['wall_seconds']:.1f} s |
| Index build peak process RSS | {index['peak_rss_mb']:.1f} MiB |
| Separate optimization attempt, ended unsuccessfully before exports | {recovery['optimization_attempt_seconds']:.1f} s |
| Gene-catalog repair and row-identity checks | {repair['repair_seconds']:.2f} s |
| Cohort preview median, 10 trials | {m['preview_p50_seconds']:.4f} s |
| Cohort preview p95, 10 trials | {m['preview_p95_seconds']:.4f} s |
| Sparse panel export | {export['elapsed_seconds']:.3f} s |
| Exported matrix shape | {export['n_obs']:,} × {export['n_vars']} |
| Export size, including metadata | {export['output_bytes']:,} bytes |
| Baseline validation process peak RSS | {benchmark['peak_rss_mb']:.1f} MiB |
| SciPy in-memory filter median | {m['scipy_filter_p50_seconds']:.6f} s |
| Rust in-memory filter median | {m['rust_filter_p50_seconds']:.6f} s |
| Complete selected-class donor pseudobulk | {benchmark['pseudobulk']['seconds']:.3f} s |

Predicate: `{json.dumps(benchmark['filters'], sort_keys=True)}`. Panel: APOE, TREM2, TYROBP, P2RY12, SST, MAPT. The cell export uses the first 5,000 matching source rows as a bounded validation workload, not a representative sample.

{optimization_section}## Verification and interpretation

The exported counts exactly match an independent AnnData backed sparse read, with matching cell/gene order. A normalized-expression subset is additionally verified across all 36,601 genes. Selected donors have disjoint training splits. One donor's pseudobulk is checked against a direct source sum. Synthetic test results are in `tests-final.log`.

These are local measurements with existing filesystem caches, not controlled cold-cache or remote-service benchmarks. Reference backed read time excludes metadata and output writing, so it is not directly comparable to end-to-end export time. Rust/SciPy medians use the same already-loaded block.

The original-to-export file-size ratio is {benchmark['source_to_export_byte_ratio']:.1f}× for this output, not a measured time or network speedup. The initial complete download is still required. Sparse batches avoid full matrix materialization; row pointers, selected IDs, and output metadata still consume memory.

## Scope and use

Implemented: local CSR slicing, indexed metadata, exact gene resolution, h5ad export/provenance, donor-disjoint splits, and donor count aggregation. Not implemented: hosted queries, gene-first matrix indexes, cross-release harmonization, biological label inference, or a graphical interface. Immune is not synonymous with pure microglia. Atlas associations are not causal perturbation labels.

See `../README.md` for CLI/notebook examples and `benchmark.json` for exact measurements. Source is in `../src/sea_ad_slice`; the Rust kernel is in `../rust/sparse_filter.rs`.

## Catalog recovery

The optimization attempt ended before exports with an incomplete catalog: cells and covering indexes were present, but the gene table was absent. The small gene table was rebuilt from the verified source in {repair['repair_seconds']:.2f} seconds; all cell row IDs were checked for complete unique coverage, and {repair['cell_ids_spot_checked']} sampled cell identifiers matched the source. The cause was not established. The API now rejects incomplete catalogs early, and the final integrated suite passes {test_count} tests.

## Review execution note

Parallel reviewers returned `WorkerDeadlineExceededError: worker execution exceeded its 898.987s remaining deadline` and `WorkerDeadlineExceededError: worker execution exceeded its 898.897s remaining deadline`. Persisted tests and partial findings were inspected, boundary issues were fixed, and integrated tests were run directly; no completed independent final audit is claimed.
'''
(root / 'results/implementation-report.md').write_text(report)
archive = root / 'results/sea-ad-slice-code.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
    files = [root / name for name in ['README.md', 'requirements.txt', 'download.py', 'verify_download.py', 'build_index.py', 'benchmark.py', 'make_report.py', 'finish_validation.py', 'repair_catalog.py', 'validate_repaired.py', 'optimize_export.py']]
    files += [root / 'data/source.json', root / 'data/download-receipt.json']
    files += list((root / 'src').rglob('*.py')) + list((root / 'tests').glob('*.py')) + list((root / 'rust').glob('*.rs'))
    files += [root / 'results' / name for name in ['implementation-report.md', 'benchmark.json', 'index-metrics.json', 'tests-final.log', 'validation-plan.md', 'catalog-repair.json', 'recovery-note.json', 'query-plan-before.json', 'benchmark.log']]
    baseline_metrics = root / 'results/baseline-benchmark.json'
    if baseline_metrics.exists():
        files.append(baseline_metrics)
    for path in files:
        package.write(path, Path('sea-ad-slice') / path.relative_to(root))
print(report)
print('Source archive:', archive, archive.stat().st_size, 'bytes')
