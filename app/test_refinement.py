import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path('/workspace/sea-ad-slice/app')
SCREENS = ROOT / 'screenshots/refinement'
SCREENS.mkdir(parents=True, exist_ok=True)
RESULTS = {'passed': [], 'page_errors': [], 'screenshots': []}


async def capture(page, name):
    path = SCREENS / f'{name}.png'
    await page.screenshot(path=str(path), full_page=False)
    RESULTS['screenshots'].append(str(path))


async def select_tab(page, label):
    await page.get_by_role('tab', name=re.compile(label, re.I)).click()


async def verify():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1366, 'height': 768}, accept_downloads=True)
        page = await context.new_page()
        page.on('pageerror', lambda error: RESULTS['page_errors'].append(str(error)))
        await page.route('**/health', lambda route: route.fulfill(status=200, json={'status': 'loading', 'message': 'Preparing source'}))
        await page.goto('http://127.0.0.1:9000/', wait_until='networkidle')
        await capture(page, 'loading-light')
        visible_text = await page.locator('body').inner_text()
        RESULTS['loading_visible_text'] = visible_text.strip()
        await page.evaluate("window.postMessage({type:'meshia.theme',theme:'dark'}, '*')")
        await capture(page, 'loading-dark')
        await page.unroute('**/health')
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_function("document.getElementById('cell-count').textContent === '36,686'", timeout=90000)
        assert await page.get_by_role('tab').count() >= 3
        assert await page.locator('select:visible').count() == 0
        text = await page.locator('body').inner_text()
        for removed in ['Define a cohort', 'Local source ready', 'Local cohort retrieval', 'SEA-AD · MTG RNA-seq']:
            assert removed not in text, removed
        assert await page.locator('footer:visible').count() == 0
        RESULTS['passed'].append('real cohort: 36,686 cells; redundant copy removed; semantic tabs; no visible native selects')
        combo = page.get_by_role('combobox').first
        await combo.focus()
        await combo.press('ArrowDown')
        assert await combo.get_attribute('aria-expanded') == 'true'
        await capture(page, 'dropdown')
        await combo.press('Escape')
        assert await combo.get_attribute('aria-expanded') == 'false'
        await combo.press('ArrowDown')
        await combo.press('Home')
        await combo.press('Escape')
        RESULTS['passed'].append('custom dropdown keyboard open, Home, Escape and focus')
        await capture(page, 'cohort-light')
        await page.evaluate("window.postMessage({type:'meshia.theme',theme:'dark'}, '*')")
        await page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
        await capture(page, 'cohort-dark')
        await select_tab(page, 'Expression')
        await page.locator('#genes').fill('APOE, TREM2')
        await page.locator('#sample-button').click()
        await page.wait_for_function("document.querySelectorAll('#sample-rows tr').length === 24", timeout=90000)
        await capture(page, 'expression-dark')
        RESULTS['passed'].append('real expression sample: 24 cells, APOE and TREM2')
        await select_tab(page, 'Export')
        await page.locator('#limit').fill('8')
        async with page.expect_response(lambda response: '/api/exports' in response.url and response.request.method == 'POST') as response_info:
            await page.locator('#export-button').click()
        response = await response_info.value
        assert response.status == 202
        job = await response.json()
        job_id = job['id']
        await page.wait_for_function("async id => { const r = await fetch('api/exports'); const d = await r.json(); const j = d.jobs.find(x => x.id === id); if (j && ['error','failed'].includes(j.status)) throw new Error(j.error || j.message); return j?.status === 'done'; }", arg=job_id, timeout=120000, polling=2000)
        await page.locator('#refresh-jobs').click()
        await capture(page, 'exports-dark')
        RESULTS['passed'].append(f'real 8-cell export completed: {job_id}')
        await select_tab(page, 'Expression')
        await page.locator('#genes').fill('NOT_A_REAL_GENE')
        await page.locator('#sample-button').click()
        await page.wait_for_function("document.querySelector('#sample-state').classList.contains('error')", timeout=30000)
        RESULTS['passed'].append('invalid gene produces visible error')
        await select_tab(page, 'Cohort')
        for width, height, theme in [(1366, 768, 'light'), (320, 740, 'light'), (320, 740, 'dark')]:
            await page.set_viewport_size({'width': width, 'height': height})
            await page.evaluate("theme => window.postMessage({type:'meshia.theme',theme}, '*')", theme)
            await page.wait_for_function('theme => document.documentElement.dataset.theme === theme', arg=theme)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}px'
            await capture(page, f'cohort-{width}-{theme}')
        RESULTS['passed'].append('1366px and 320px theme/layout checks with no page overflow')
        assert not RESULTS['page_errors'], RESULTS['page_errors']
        await browser.close()


async def main():
    try:
        await verify()
    except Exception as error:
        RESULTS['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        (ROOT / 'refinement-test-results.json').write_text(json.dumps(RESULTS, indent=2))
        print(json.dumps(RESULTS, indent=2), flush=True)


asyncio.run(main())
