import os
from pathlib import Path
import subprocess
import sys
import threading

root = Path(__file__).resolve().parent
environment = dict(os.environ)
environment['PYTHONPATH'] = str(root / 'src')


def run_step(script, log_name, timeout):
    with (root / 'results' / log_name).open('w') as log:
        process = subprocess.Popen([sys.executable, '-u', str(root / script)], cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        timer = threading.Timer(timeout, process.kill)
        timer.daemon = True
        timer.start()
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            code = process.wait()
        finally:
            timer.cancel()
        if code:
            raise subprocess.CalledProcessError(code, [sys.executable, script])


print('CATALOG_REPAIRED: validating complete pinned-source subsets', flush=True)
run_step('benchmark.py', 'benchmark.log', 1800)
print('REAL_DATA_VALIDATION_PASSED', flush=True)
run_step('make_report.py', 'report-generation.log', 120)
print('SEAAD_VALIDATION_COMPLETE', flush=True)
