import json
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent
screens = root / 'screenshots'
screens.mkdir(exist_ok=True)
results = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
    context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:9000/', wait_until='networkidle')
    page.wait_for_function("document.getElementById('cell-count').textContent === '36,686'", timeout=90000)
    page.locator('#genes').fill('APOE, TREM2')
    page.locator('#sample-button').click()
    page.wait_for_function("document.querySelectorAll('#sample-rows tr').length === 24", timeout=90000)
    page.screenshot(path=str(screens / 'desktop-light.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    results.append('desktop cohort and real expression read')
    page.locator('#limit').fill('32')
    page.locator('#export-button').click()
    page.wait_for_function("[...document.querySelectorAll('.job-status')].some(x => ['queued','running','done'].includes(x.textContent))", timeout=15000)
    page.wait_for_function("document.querySelectorAll('.job-links a').length >= 4", timeout=120000)
    with page.expect_download() as download:
        page.locator('.job-links a').first.click()
    artifact = download.value
    artifact.save_as(str(root / 'browser-export.h5ad'))
    assert (root / 'browser-export.h5ad').stat().st_size > 0
    results.append('browser export queue and H5ad download')
    page.evaluate("window.postMessage({type:'meshia.theme',theme:'dark'}, '*')")
    page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
    page.screenshot(path=str(screens / 'desktop-dark.png'), full_page=True)
    results.append('dark theme')
    page.set_viewport_size({'width': 320, 'height': 740})
    page.screenshot(path=str(screens / 'mobile-dark.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not page.locator('#parameter-details').evaluate('(element) => element.open')
    page.locator('.parameter-summary').click()
    assert page.locator('#parameter-details').evaluate('(element) => element.open')
    results.append('320px layout, no horizontal overflow, usable filter disclosure')
    page.evaluate("window.postMessage({type:'meshia.theme',theme:'light'}, '*')")
    page.screenshot(path=str(screens / 'mobile-light.png'), full_page=True)
    page.set_viewport_size({'width': 1366, 'height': 768})
    page.locator('#genes').fill('NOT_A_REAL_GENE')
    page.locator('#sample-button').click()
    page.wait_for_function("document.querySelector('#sample-state').classList.contains('error')", timeout=30000)
    assert 'missing or ambiguous' in page.locator('#sample-state').inner_text()
    results.append('visible invalid-gene error')
    assert not errors, errors
    browser.close()
(root / 'browser-test-results.json').write_text(json.dumps({'passed': results, 'page_errors': errors}, indent=2))
print(json.dumps({'passed': results, 'page_errors': errors}, indent=2))
