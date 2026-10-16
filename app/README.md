# SEA-AD explorer

The live workspace app is `/lab/sea-ad-explorer`. It uses the verified local MTG source and metadata catalog, not mock data.

## Try it

1. Start with the Immune subclass and the reference-cohort exclusion enabled. Preview the cohort and donor counts.
2. Enter exact gene symbols or feature IDs, select raw `UMIs` or normalized `X`, and read the first 24 matching cells.
3. Choose a cell limit and queue an export. Download its AnnData file and provenance JSON after completion.

The app limits exports to 10,000 cells and 32 genes, with one export running at a time and at most three active/queued. Source order is retained; these limited reads are not representative random samples. Donor splits require at least three selected donors. Immune is not necessarily pure microglia.

Advanced filters accept exact scalar values or null. The underlying CLI supports additional operators. Interactive queries have a 25-second SQLite budget; narrow the cohort if a query exceeds it. Export jobs have a 20-minute timeout. Saved job states persist in `app/exports`; interrupted exports are not silently replayed after restart.

## Run

From `/workspace/sea-ad-slice`, with the scientific dependencies in the parent `requirements.txt` and web dependencies in `app/requirements.txt` installed:

```bash
PYTHONPATH=src python -m uvicorn app.server:app --host 127.0.0.1 --port 9000
```

The source and catalog remain read-only. The app writes new exports only under `app/exports`.

## Verification

- `app/validation-report.json`: default cohort 36,686 cells and 84 donors; both expression layers exactly match independent HDF5 reads; a downloaded 64-cell export exactly matches source counts; error, empty-cohort, recipe and example-download checks pass.
- `app/browser-test-results.json`: actual Chromium interaction tests for cohort preview, expression reads, queued export/download, visible input errors, light/dark themes, and a 320-pixel layout without horizontal overflow; no page JavaScript errors.
- `app/screenshots`: browser screenshots from the layout tests.

Tests use `app/test_api.py` and `app/test_browser.py`; the latter additionally requires Playwright and its Chromium browser. The original 119-test core suite is unchanged.
