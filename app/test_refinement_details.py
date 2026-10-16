import asyncio
import json
from pathlib import Path

from PIL import Image, ImageChops
from playwright.async_api import async_playwright

ROOT = Path('/workspace/sea-ad-slice/app')
RESULT = {'passed': []}


def inspect_loading_image(name, background):
    image = Image.open(ROOT / f'screenshots/refinement/{name}.png').convert('RGB')
    difference = ImageChops.difference(image, Image.new('RGB', image.size, background))
    bounds = difference.getbbox()
    assert bounds is not None
    left, top, right, bottom = bounds
    assert right - left <= 45 and bottom - top <= 45, bounds
    assert abs((left + right) / 2 - image.width / 2) < 2, bounds
    assert abs((top + bottom) / 2 - image.height / 2) < 2, bounds
    RESULT['passed'].append(f'{name}: only centered square pixels; theme-matched background')


async def main():
    inspect_loading_image('loading-light', '#f7fafb')
    inspect_loading_image('loading-dark', '#071015')
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1366, 'height': 768}, reduced_motion='reduce')
        await page.route('**/health', lambda route: route.fulfill(status=200, json={'status': 'loading'}))
        await page.goto('http://127.0.0.1:9000/', wait_until='networkidle')
        assert await page.locator('.loading-square').evaluate("element => getComputedStyle(element).animationName") == 'none'
        assert await page.locator('#app-shell').evaluate('element => element.inert')
        RESULT['passed'].append('reduced-motion loader; background app inert until ready')
        await page.unroute('**/health')
        await page.route('**/health', lambda route: route.fulfill(status=200, json={'status': 'error', 'message': 'Source unavailable'}))
        await page.reload(wait_until='networkidle')
        await page.get_by_role('button', name='Retry', exact=True).wait_for()
        assert 'Source unavailable' in await page.locator('#preview-state').inner_text()
        await page.screenshot(path=str(ROOT / 'screenshots/refinement/startup-error.png'))
        RESULT['passed'].append('startup failure exposes actionable Retry instead of endless loading')
        await page.unroute('**/health')
        await page.get_by_role('button', name='Retry', exact=True).click()
        await page.wait_for_function("document.getElementById('cell-count').textContent === '36,686'", timeout=90000)
        combo = page.get_by_role('combobox', name='Subclass', exact=True)
        initial = await page.locator('#subclass').input_value()
        await combo.press('ArrowDown')
        await combo.press('Home')
        await combo.press('Enter')
        assert await page.locator('#subclass').input_value() != initial
        await combo.press('ArrowDown')
        await combo.press('i')
        await combo.press('Enter')
        assert await page.locator('#subclass').input_value() == 'Immune'
        await page.locator('#preview-button').click()
        await page.wait_for_function("document.getElementById('cell-count').textContent === '36,686' && !document.getElementById('preview-content').hidden", timeout=90000)
        RESULT['passed'].append('custom select commits with Enter and typeahead restores Immune')
        chevron = await page.locator('#subclass-button .select-chevron').bounding_box()
        button = await combo.bounding_box()
        assert button['x'] + button['width'] - chevron['x'] - chevron['width'] >= 12
        help_button = page.get_by_role('button', name='About donor counts', exact=True)
        await help_button.focus()
        assert await page.get_by_role('tooltip').is_visible()
        await help_button.press('Escape')
        assert not await page.get_by_role('tooltip').is_visible()
        RESULT['passed'].append('chevron right inset >=12px; tooltip focus and Escape')
        await page.get_by_role('tab', name='Exports', exact=True).click()
        assert not await page.locator('#sample-button').is_visible()
        assert not await page.locator('#preview-button').is_visible()
        await page.locator('.job').first.wait_for()
        async with page.expect_download() as download_info:
            await page.locator('.job').filter(has=page.locator('[href*="07538e24f14e4f908a64119edccc441a/file"]')).get_by_role('link', name='AnnData ↓').click()
        download = await download_info.value
        path = ROOT / 'refinement-export.h5ad'
        await download.save_as(str(path))
        import anndata
        data = anndata.read_h5ad(path)
        assert data.shape == (8, 2), data.shape
        RESULT['passed'].append('browser AnnData download reopened: 8 cells × 2 genes')
        await page.set_viewport_size({'width': 320, 'height': 740})
        await page.locator('.parameter-summary').click()
        assert await page.locator('#parameter-details').evaluate('element => element.open')
        await page.get_by_role('combobox', name='Layer', exact=True).click()
        popup = page.locator('#layer-list')
        box = await popup.bounding_box()
        assert box['x'] >= 0 and box['x'] + box['width'] <= 320
        assert box['y'] >= 0 and box['y'] + box['height'] <= 740
        await page.screenshot(path=str(ROOT / 'screenshots/refinement/mobile-controls.png'))
        RESULT['passed'].append('mobile disclosure and dropdown fit within 320px viewport')
        await browser.close()
    (ROOT / 'refinement-detail-results.json').write_text(json.dumps(RESULT, indent=2))
    print(json.dumps(RESULT, indent=2), flush=True)


asyncio.run(main())
