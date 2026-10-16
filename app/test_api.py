import json
from pathlib import Path
import time
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:9000/'


def read(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(BASE + path, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.status, json.load(response)


def rejected(path, data, code):
    try:
        read(path, data)
    except urllib.error.HTTPError as error:
        assert error.code == code
        return json.load(error)
    raise AssertionError('Invalid input was accepted')


assert read('health')[1]['status'] == 'ready'
_, config = read('api/config')
assert config['source']['n_obs'] == 1178694
filters = {'Subclass': 'Immune', 'Neurotypical reference': False}
_, preview = read('api/preview', {'filters': filters})
assert preview['cells'] == 36686 and len(preview['groups']) == 84
samples = {}
for layer in ['UMIs', 'X']:
    _, sample = read('api/sample', {'filters': filters, 'genes': ['APOE', 'TREM2'], 'layer': layer})
    assert sample['cells'] == 24
    samples[layer] = sample
print('Preview and both real expression layers passed', flush=True)
_, empty = read('api/preview', {'filters': {'Subclass': 'not-a-real-subclass'}})
assert empty['cells'] == 0
rejected('api/sample', {'filters': filters, 'genes': ['NOT_A_REAL_GENE']}, 400)
rejected('api/exports', {'filters': filters, 'genes': ['APOE'], 'limit': 10001}, 400)
rejected('api/preview', {'filters': {'unknown_column': 1}}, 400)
status, job = read('api/exports', {'filters': filters, 'genes': ['APOE', 'TREM2'], 'layer': 'UMIs', 'limit': 64, 'engine': 'scipy', 'split_seed': None})
assert status == 202
print('Queued real test export', job['id'], flush=True)
result = {'config_ok': True, 'preview_cells': preview['cells'], 'preview_donors': len(preview['groups']), 'samples': samples, 'empty_cohort_ok': True, 'invalid_inputs_rejected': True, 'test_export_id': job['id']}
Path('app/api-test-results.json').write_text(json.dumps(result, indent=2))
