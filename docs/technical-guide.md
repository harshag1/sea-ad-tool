# SEA-AD Slice: technical guide

This is the original technical README, preserved for the command examples and implementation details. For the plain-language overview and current availability, start with [the main README](../README.md).

**Scope of this copy:** the metadata catalogue and code are present, but the full expression source and generated expression exports are not. Dependencies are not guaranteed to be installed. Commands below assume the repository is at `/workspace/sea-ad-slice`; adjust that path if you put it elsewhere. Expression-reading commands require the original source file. Historical validation and benchmark records describe the original workspace, not a fresh validation of this copy.

A local, notebook-first query tool for the complete June 2026 SEA-AD MTG final-QC RNA object. It indexes metadata without loading expression matrices, retrieves sparse cell/gene subsets, streams matrix batches, and exports standard AnnData files with provenance.

## Workspace layout

- `data/SEAAD_MTG_RNAseq_final-nuclei.2026-06-22.h5ad`: complete original object, 32,978,570,763 bytes.
- `data/source.json` and `data/download-receipt.json`: source URL, object identity, and integrity evidence.
- `data/mtg.sqlite`: reusable cell/gene metadata catalog and indexes.
- `src/sea_ad_slice`: Python API and CLI.
- `rust/sparse_filter.rs`: compiled Rust CSR gene-selection kernel, with no third-party Rust dependencies.
- `tests/`: differential correctness and boundary tests.
- `results/`: verification outputs and measured benchmarks.

## Run from this checkout

A clean environment needs the packages in `requirements.txt`, plus `rustc` if you want to compile the optional native kernel. Do not assume these dependencies are installed in this copy.

```bash
cd /workspace/sea-ad-slice
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
rustc --crate-type cdylib -C opt-level=3 rust/sparse_filter.rs -o rust/libsparse_filter.so
python -m sea_ad_slice summary --db data/mtg.sqlite
```

`--engine scipy` avoids requiring the Rust shared library. The current distribution is a source checkout, not a portable compiled wheel.

## Preview a cohort

```bash
python -m sea_ad_slice preview --db data/mtg.sqlite --filters '{"Subclass":"Immune","Neurotypical reference":false}'
```

The `Immune` subclass is not an assertion that every selected cell is microglia. Use `Supertype` and the release taxonomy when a more specific population is needed. Explicitly exclude young neurotypical reference donors for an aged-cohort analysis.

Filters are parameterized conjunctions. Values can be exact scalars, lists, null, or comparison dictionaries using `eq`, `ne`, `gt`, `gte`, `lt`, and `lte`. Null matches missing metadata; SQL comparison with null remains unknown. Categorical pathology fields must be matched by documented labels, not compared as numbers.

```json
{"Subclass":"Immune","Overall AD neuropathological Change":["High","Intermediate"],"Neurotypical reference":false}
```

Use `summary` to discover exact metadata field names and matrix layers. Gene symbols and feature identifiers are resolved exactly; missing, ambiguous, or duplicated gene selections raise errors rather than silently disappearing.

## Export selected raw counts

```bash
python -m sea_ad_slice export --db data/mtg.sqlite --filters '{"Subclass":"Immune","Neurotypical reference":false}' --genes APOE TREM2 TYROBP P2RY12 --layer UMIs --output results/my_immune_panel.h5ad --split-seed 42
```

The chosen layer becomes the output `X`; source values and their dtype are preserved. Source `X` is normalized expression and `UMIs` is the raw-count layer in this pinned file. No transformation is inferred from floating-point versus integer storage: the source stores both matrices as float64.

Exports preserve selected cell/gene metadata, add source row/column IDs, and write a JSON recipe both inside `uns` and beside the output. Unused categorical labels are omitted through selective label reads, preventing a small subset from inheriting the source's million-label barcode vocabulary. Actual annotation values and relative category ordering are preserved; integer category codes are local to each subset, so join on labels or canonical IDs. Existing outputs are not overwritten. Embeddings and neighbor graphs are deliberately omitted; they are not recomputed or silently represented as subset-specific embeddings.

`--limit N` takes the first N matching rows in source order. It is for bounded previews and tests, not a biologically representative sampler. Donor splits are deterministic and disjoint for the same selected donor set and seed; they are not pathology-stratified. Changing the donor set can change assignments. Fit preprocessing on training donors only.

## Notebook / streaming API

```python
from sea_ad_slice import Catalog

catalog = Catalog('/workspace/sea-ad-slice/data/mtg.sqlite')
filters = {'Subclass': 'Immune', 'Neurotypical reference': False}
preview = catalog.preview(filters)
rows = catalog.rows(filters)
columns = catalog.genes(['APOE', 'TREM2', 'TYROBP'])
for source_rows, matrix in catalog.batches(rows, columns, layer='UMIs', batch_rows=2048):
    consume(source_rows, matrix)
```

`consume` represents the caller's own training or analysis code. Batches remain CSR sparse matrices. The backend coalesces nearby selected source rows, caps each ordinary read at a configurable nonzero budget, and never densifies a source matrix. It keeps the source `indptr` in memory, so memory includes O(number of source cells) row pointers, O(selected rows) IDs, and bounded sparse batches, not a constant independent of atlas size. Export metadata also scales with the selected output.

## Donor pseudobulk

```bash
python -m sea_ad_slice pseudobulk --db data/mtg.sqlite --filters '{"Subclass":"Immune","Neurotypical reference":false}' --genes APOE TREM2 TYROBP --layer UMIs --output results/my_pseudobulk.h5ad
```

This sums raw counts by donor and records cell counts. It checks count validity and conservatively guards int64 overflow. It is an aggregation product, not a differential-expression model, confounder correction, or causal result. Integer-valued data alone do not establish biological raw-count semantics; choose the documented layer.

## Rebuild / recover

```bash
python download.py
python verify_download.py
python -m sea_ad_slice index data/SEAAD_MTG_RNAseq_final-nuclei.2026-06-22.h5ad --db data/mtg.sqlite
python -m pytest tests -q
```

The downloader uses exact HTTP byte ranges tied to a pinned ETag and tracks completed chunks. An interrupted download resumes its unfinished ranges. The source SHA256 is recorded locally. `verify_download.py` independently checks the publisher's multipart ETag using the verified 8 MiB part layout; it fails rather than treating an unknown multipart layout as verified.

Source size and mtime protect the local metadata index from accidental stale use. This is not an adversarial content-integrity guarantee. Source relocation or changed identity requires rebuilding the index. The API rejects incomplete catalogs before running queries. `PYTHONPATH=src python repair_catalog.py` can recover a missing gene lookup table after verifying source identity, full unique cell-row coverage, and sampled cell IDs; it does not repair arbitrary corruption. Index construction is atomic at completion and restarts from scratch after interruption. Compact covering indexes support common subclass/supertype, reference-cohort, and donor predicates without wide-table lookups. Re-running the `index` command on a valid existing catalog adds missing query indexes without rebuilding source metadata. Do not run concurrent writers against the same destination.

## Performance and scope

Read `results/benchmark.json` for measured real-data timings once validation completes. Metadata indexing and download costs are one-time setup, not hidden query speedups. Benchmarks use existing filesystem caches, not controlled cold-cache conditions. Rust and SciPy filtering are measured separately; a native implementation is not presumed faster.

This MVP supports this local CSR h5ad workflow. It is not a hosted remote atlas service, a gene-first CSC index, a graphical cohort builder, or a cross-release taxonomy harmonizer. Broad gene-panel queries can still scan substantial CSR data. Controlled-access raw sequencing is not included.

Source: https://brain-map.org/consortia/sea-ad/our-data

Dataset documentation: https://cdn.prod.website-files.com/689cfbd308fa7373b604d290/6a458531b71c8d1b58bf9235_sea-ad_singlecellprofiling-awsdocumentationtutorial_06302026.pdf

Follow the Allen Institute terms and citation policy for downstream use. Dataset rights are separate from this implementation.
