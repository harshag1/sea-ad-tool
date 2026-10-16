import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path(__file__).resolve().parent
STATIC = APP_ROOT / 'static'
EXPORTS = APP_ROOT / 'exports'
EXPORTS.mkdir(parents=True, exist_ok=True)
MAX_CELLS = 10000
MAX_GENES = 32
DEFAULT_GENES = ['APOE', 'TREM2', 'TYROBP', 'P2RY12', 'SST', 'MAPT']
STATE = {'status': 'loading', 'message': 'Opening the verified metadata catalog'}
JOBS = {}
JOB_LOCK = threading.RLock()
DATA_LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=1)
CATALOG = None
CONFIG = None


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def save_job(job):
    directory = EXPORTS / job['id']
    directory.mkdir(exist_ok=True)
    temporary = directory / 'job.json.partial'
    temporary.write_text(json.dumps(job, indent=2))
    temporary.replace(directory / 'job.json')


def initialize():
    global CATALOG, CONFIG
    try:
        import sqlite3
        from sea_ad_slice import Catalog
        from sea_ad_slice.core import quote

        class BoundedCatalog(Catalog):
            def connect(self):
                connection = super().connect()
                deadline = time.monotonic() + 8
                connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 2000)
                return connection

            def preview(self, filters=None, group_by='Donor ID'):
                if group_by not in self.fields:
                    raise ValueError(f'Unknown grouping field: {group_by}')
                filters = filters or {}
                started = time.perf_counter()
                where, values = self.predicate(filters)
                covered = {'Subclass', 'Supertype', 'Donor ID', 'Neurotypical reference'}
                index = ''
                if set(filters) <= covered and group_by == 'Donor ID':
                    name = 'cohort_supertype_cover' if 'Supertype' in filters else 'cohort_subclass_cover' if 'Subclass' in filters else 'cohort_donor_cover'
                    index = f' INDEXED BY {quote(name)}'
                with self.connect() as connection:
                    groups = connection.execute(f'SELECT {quote(group_by)}, COUNT(*) FROM cells{index} WHERE {where} GROUP BY {quote(group_by)} ORDER BY COUNT(*) DESC', values).fetchall()
                return {'cells': sum(number for _, number in groups), 'group_by': group_by, 'groups': [{'value': value, 'cells': number} for value, number in groups], 'query_seconds': time.perf_counter() - started}

        CATALOG = BoundedCatalog(ROOT / 'data/mtg.sqlite')
        CATALOG.check_source()
        fields = []
        names = ['Subclass', 'Supertype', 'Donor ID']
        covering = {'Subclass': 'cohort_subclass_cover', 'Supertype': 'cohort_supertype_cover', 'Donor ID': 'cohort_donor_cover'}
        for name in names:
            if name not in CATALOG.fields:
                continue
            with CATALOG.connect() as connection:
                rows = connection.execute(f'SELECT {quote(name)}, COUNT(*) FROM cells INDEXED BY {quote(covering[name])} GROUP BY {quote(name)} ORDER BY COUNT(*) DESC LIMIT 500').fetchall()
            fields.append({'name': name, 'values': [{'value': value, 'cells': count} for value, count in rows]})
        benchmark = json.loads((ROOT / 'results/benchmark.json').read_text())
        CONFIG = {
            'status': 'ready',
            'source': {'release': 'June 2026 · MTG final-QC RNA', 'n_obs': CATALOG.schema['n_obs'], 'n_vars': CATALOG.schema['n_vars'], 'donors': benchmark['donors'], 'layers': [{'value': 'UMIs', 'label': 'Raw counts (UMIs)'}, {'value': 'X', 'label': 'Normalized expression (X)'}]},
            'fields': fields,
            'defaults': {'filters': {'Subclass': 'Immune', 'Neurotypical reference': False}, 'genes': DEFAULT_GENES, 'layer': 'UMIs', 'limit': 1000},
            'limits': {'max_cells': MAX_CELLS, 'max_genes': MAX_GENES},
            'files': [{'name': 'Verified raw-count panel', 'url': 'api/examples/panel', 'description': '5,000 cells × 6 genes, AnnData'}, {'name': 'Verified donor pseudobulk', 'url': 'api/examples/pseudobulk', 'description': '84 donors × 6 genes, raw-count sums'}, {'name': 'Source code bundle', 'url': 'api/examples/source', 'description': 'Python, Rust, tests and reproducibility records'}, {'name': 'Implementation report', 'url': 'api/examples/report', 'description': 'Measured results and validation details'}],
            'benchmark': benchmark['measurements'],
        }
        with JOB_LOCK:
            for path in EXPORTS.glob('*/job.json'):
                if not re.fullmatch(r'[a-f0-9]{32}', path.parent.name):
                    continue
                try:
                    job = json.loads(path.read_text())
                    if job['status'] in ['queued', 'running']:
                        job.update(status='interrupted', message='App restarted. Submit a new export to retry.')
                        save_job(job)
                    JOBS[job['id']] = job
                except (ValueError, KeyError):
                    continue
        STATE.update(status='ready', message='Verified local source and catalog ready')
    except Exception as error:
        STATE.update(status='error', message=f'Could not open the source catalog: {type(error).__name__}')
        print(f'Initialization failed: {error}', flush=True)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=initialize, daemon=True).start()
    yield
    EXECUTOR.shutdown(wait=False, cancel_futures=True)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def security_headers(request, call_next):
    if request.method == 'POST':
        if request.headers.get('sec-fetch-site') == 'cross-site' or not request.headers.get('content-type', '').lower().startswith('application/json'):
            return JSONResponse({'error': 'Only same-app JSON requests are accepted'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.exception_handler(ValueError)
@app.exception_handler(Exception)
async def handle_error(request, error):
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return JSONResponse({'error': str(error)}, status_code=400)
    if 'interrupted' in str(error).lower():
        return JSONResponse({'error': 'This query exceeded the interactive time budget. Narrow the cohort and try again.'}, status_code=408)
    print(f'Request failed: {type(error).__name__}: {error}', flush=True)
    return JSONResponse({'error': 'The operation could not finish. Try a smaller cohort or gene panel.'}, status_code=500)


def require_ready():
    if STATE['status'] != 'ready':
        raise ValueError(STATE['message'])


async def payload(request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 32768:
            raise ValueError('Request exceeds 32 KB')
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object')
    return data


def valid_filters(data):
    filters = data.get('filters', {})
    if not isinstance(filters, dict) or len(filters) > 12:
        raise ValueError('Use an object with at most 12 metadata filters')
    for key, value in filters.items():
        if key not in CATALOG.fields:
            raise ValueError(f'Unknown metadata field: {key}')
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError('Interactive filters accept exact scalar values or null')
        if isinstance(value, str) and len(value) > 300:
            raise ValueError('Metadata value is too long')
        if isinstance(value, float) and not __import__('math').isfinite(value):
            raise ValueError('Metadata values must be finite')
    CATALOG.predicate(filters)
    return filters


def valid_expression(data):
    filters = valid_filters(data)
    genes = data.get('genes', DEFAULT_GENES)
    if not isinstance(genes, list) or not 1 <= len(genes) <= MAX_GENES or any(not isinstance(gene, str) or not 1 <= len(gene) <= 100 for gene in genes):
        raise ValueError(f'Select 1–{MAX_GENES} exact gene names or IDs')
    columns = CATALOG.genes(genes)
    layer = data.get('layer', 'UMIs')
    if layer not in ['UMIs', 'X']:
        raise ValueError('Layer must be UMIs or X')
    return filters, genes, columns, layer


def sample(data):
    import h5py
    import numpy as np
    from scipy import sparse
    from sea_ad_slice.core import read_frame_rows
    started = time.perf_counter()
    with DATA_LOCK:
        filters, genes, columns, layer = valid_expression(data)
        rows = CATALOG.rows(filters, limit=24)
        batches = [matrix for _, matrix in CATALOG.batches(rows, columns, layer=layer, engine='scipy')]
        matrix = sparse.vstack(batches).toarray() if batches else np.zeros((0, len(genes)))
        with h5py.File(CATALOG.source, 'r') as handle:
            obs = handle['obs']
            index = obs[obs.attrs['_index']]
            ids = index[rows].astype(str).tolist() if len(rows) else []
            donors = __import__('anndata').io.read_elem(obs['Donor ID'])[rows]
            subclasses = __import__('anndata').io.read_elem(obs['Subclass'])[rows]
        result = [{'cell_id': ids[i], 'donor': str(donors[i]), 'subclass': str(subclasses[i]), 'values': matrix[i].tolist()} for i in range(len(rows))]
    return {'rows': result, 'genes': genes, 'layer': layer, 'source_rows': rows.tolist(), 'seconds': time.perf_counter() - started, 'cells': len(rows), 'sample_note': 'First 24 matching source rows, not a representative sample. Source values are unchanged.'}


def run_export(job_id, data):
    with JOB_LOCK:
        job = JOBS[job_id]
        job.update(status='running', message='Reading selected source cells and writing sparse AnnData')
        save_job(job)
    directory = EXPORTS / job_id
    output = directory / 'panel.h5ad'
    command = [sys.executable, '-m', 'sea_ad_slice', 'export', '--db', str(CATALOG.database), '--filters', json.dumps(data['filters']), '--genes', *data['genes'], '--layer', data['layer'], '--limit', str(data['limit']), '--engine', data['engine'], '--output', str(output)]
    if data['split_seed'] is not None:
        command.extend(['--split-seed', str(data['split_seed'])])
    try:
        with (directory / 'export.log').open('w') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)
        result = json.loads(output.with_suffix('.h5ad.json').read_text())
        result['output_bytes_at_creation'] = result['output_bytes']
        result['output_bytes'] = output.stat().st_size
        output.with_suffix('.h5ad.json').write_text(json.dumps(result, indent=2))
        with JOB_LOCK:
            job.update(status='done', message='Sparse export ready', result={key: result[key] for key in ['n_obs', 'n_vars', 'output_bytes', 'elapsed_seconds']}, download_url=f'api/exports/{job_id}/file', recipe_url=f'api/exports/{job_id}/recipe')
            save_job(job)
    except subprocess.TimeoutExpired:
        with JOB_LOCK:
            job.update(status='error', error='Export exceeded 20 minutes. Use fewer cells or genes.', message='Export stopped')
            save_job(job)
    except Exception as error:
        message = 'Export failed. Use a smaller selection and try again.'
        if isinstance(error, subprocess.CalledProcessError):
            last = (directory / 'export.log').read_text()[-3000:].strip().splitlines()
            if last and last[-1].startswith(('ValueError:', 'FileExistsError:')):
                message = last[-1][:400]
        with JOB_LOCK:
            job.update(status='error', error=message, message='Export failed')
            save_job(job)


@app.get('/health')
def health():
    return dict(STATE)


@app.get('/api/config')
def config():
    if STATE['status'] != 'ready':
        return JSONResponse(dict(STATE), status_code=503)
    return CONFIG


@lru_cache(maxsize=64)
def cached_preview(selection):
    return CATALOG.preview(json.loads(selection))


@app.post('/api/preview')
async def preview(request: Request):
    require_ready()
    filters = valid_filters(await payload(request))
    selection = json.dumps(filters, sort_keys=True)
    try:
        return await asyncio.wait_for(run_in_threadpool(cached_preview, selection), timeout=10)
    except asyncio.TimeoutError:
        return JSONResponse({'error': 'This query took too long. Narrow the filters and try again.'}, status_code=408)


@app.post('/api/sample')
async def expression_sample(request: Request):
    require_ready()
    return await run_in_threadpool(sample, await payload(request))


@app.get('/api/exports')
def exports():
    with JOB_LOCK:
        return {'jobs': json.loads(json.dumps(sorted(JOBS.values(), key=lambda job: job['created_at'], reverse=True)[:20]))}


@app.post('/api/exports')
async def create_export(request: Request):
    require_ready()
    data = await payload(request)
    filters, genes, columns, layer = await run_in_threadpool(valid_expression, data)
    limit = data.get('limit', 1000)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_CELLS:
        raise ValueError(f'Cell limit must be 1–{MAX_CELLS}')
    engine = data.get('engine', 'scipy')
    if engine not in ['scipy', 'rust']:
        raise ValueError('Engine must be scipy or rust')
    seed = data.get('split_seed')
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2147483647):
        raise ValueError('Split seed must be a nonnegative 32-bit integer')
    selected = await run_in_threadpool(CATALOG.rows, filters, 1)
    if len(selected) == 0:
        raise ValueError('No cells match the selected filters')
    normalized = {'filters': filters, 'genes': genes, 'layer': layer, 'limit': limit, 'engine': engine, 'split_seed': seed}
    with JOB_LOCK:
        if sum(job['status'] in ['queued', 'running'] for job in JOBS.values()) >= 3:
            return JSONResponse({'error': 'Three exports are already queued or running. Wait for one to finish.'}, status_code=429)
        if len(JOBS) >= 100:
            return JSONResponse({'error': 'The app has reached its saved-export limit. Existing downloads remain available.'}, status_code=429)
        job_id = uuid.uuid4().hex
        job = {'id': job_id, 'status': 'queued', 'created_at': timestamp(), 'message': 'Waiting for the export worker', 'request': normalized}
        JOBS[job_id] = job
        save_job(job)
        EXECUTOR.submit(run_export, job_id, normalized)
    return JSONResponse(job, status_code=202)


def find_job(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        return None
    with JOB_LOCK:
        job = JOBS.get(job_id)
        return json.loads(json.dumps(job)) if job else None


@app.get('/api/exports/{job_id}')
def export_status(job_id: str):
    job = find_job(job_id)
    return job if job else JSONResponse({'error': 'Export not found'}, status_code=404)


@app.get('/api/exports/{job_id}/{kind}')
def download_export(job_id: str, kind: str):
    job = find_job(job_id)
    if not job or job['status'] != 'done' or kind not in ['file', 'recipe']:
        return JSONResponse({'error': 'Completed export not found'}, status_code=404)
    name = 'panel.h5ad' if kind == 'file' else 'panel.h5ad.json'
    return FileResponse(EXPORTS / job_id / name, filename=f'sea-ad-{job_id[:8]}.{ "h5ad" if kind == "file" else "json"}')


@app.get('/api/examples/{name}')
def example(name: str):
    files = {'panel': 'immune_panel.h5ad', 'pseudobulk': 'immune_pseudobulk.h5ad', 'source': 'sea-ad-slice-code.zip', 'report': 'implementation-report.md'}
    if name not in files:
        return JSONResponse({'error': 'Example not found'}, status_code=404)
    path = ROOT / 'results' / files[name]
    return FileResponse(path, filename=path.name)


@app.get('/')
def index():
    path = STATIC / 'index.html'
    return FileResponse(path) if path.exists() else HTMLResponse('<!doctype html><html><title>SEA-AD explorer</title><body><h1>SEA-AD explorer</h1><p>Preparing the cohort explorer. Reload shortly.</p></body></html>')


@app.get('/{name}')
def static_file(name: str):
    if name not in ['app.css', 'app.js']:
        return JSONResponse({'error': 'Not found'}, status_code=404)
    return FileResponse(STATIC / name)
