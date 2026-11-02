"""Focused workspace usability checks. Uses the same optional Playwright setup as
FRONTEND_TESTING.md; all routing and OSM tiles are mocked, never prefetched.
"""
import base64
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get('DQ_TEST_URL', 'http://localhost:8000')
CHROME = os.environ.get('DQ_CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True)
        context = browser.new_context(viewport={'width':1440, 'height':1050})
        tile = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1kAAAAASUVORK5CYII=')
        context.route('https://tile.openstreetmap.org/**',lambda r:r.fulfill(content_type='image/png',body=tile))
        page = context.new_page()
        errors, calls, created = [], [], None
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            calls.append(r.request.url)
            quest = context.request.get(r.request.url.replace('walking-route/','')).json()
            r.fulfill(json={'status':'available','route':quest['path'],'way_points':list(range(len(quest['path']['coordinates']))),'distance_m':1608.1,'duration_s':1157.8,
                'notice':'Mock route estimate; entrances not verified.','warnings':[],'waypoints':[{'displacement_m':2.99}]})
        page.route('**/walking-route/',route)
        def idle(): page.wait_for_function("!document.querySelector('main').hasAttribute('aria-busy')")
        try:
            page.goto(BASE); idle()
            page.get_by_role('button',name='Trinity College Dublin',exact=True).click()
            with page.expect_response(lambda r:r.url.endswith('/api/adventures/') and r.request.method=='POST') as response:
                page.locator('#generate').click(); idle()
            created = response.value.json()['id']
            page.wait_for_selector('#walking-summary:not([hidden])')
            assert page.locator('#builder').is_hidden()
            page.wait_for_timeout(300)
            before = page.locator('#map').bounding_box()
            page.locator('#stop-list input').last.check(); idle()
            after = page.locator('#map').bounding_box()
            assert abs(before['y']-after['y']) < 5, {'before':before,'after':after,'windowScroll':page.evaluate('scrollY'),'panel':page.locator('#adventure-section').bounding_box()}
            assert after['y'] >= 0 and after['y']+after['height'] <= 1050
            page.locator('#stop-list li').first.focus()
            page.locator('#stop-list li').first.press('Enter')
            assert page.locator('.focused-pin').count()==1
            assert page.locator('.leaflet-popup').is_visible()
            page.locator('.leaflet-popup-close-button').click()
            page.locator('#map-edit').click()
            page.locator('#radius').select_option('1000')
            page.once('dialog',lambda d:d.accept())
            page.locator('#apply-regenerate').click();idle()
            page.wait_for_selector('#walking-summary:not([hidden])')
            assert page.locator('#builder').is_hidden()
            assert len(calls)==2
            for width,height,label in [(1440,1050,'desktop'),(820,1180,'tablet'),(390,844,'mobile')]:
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_timeout(300)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),label
                page.locator('#map-panel').scroll_into_view_if_needed()
                page.screenshot(path=f'/tmp/dq-workspace-{label}.png',full_page=True)
            assert page.locator('#mobile-next-slot #next-discovery').is_visible()
            assert not page.locator('#journey-details').evaluate('(e)=>e.open')
            next_name = page.locator('#next-name').inner_text()
            map_box = page.locator('#map').bounding_box()
            assert map_box['height'] >= 320
            quick_box = page.locator('#quick-visit').bounding_box()
            assert quick_box['height']>=44
            assert quick_box['y']-map_box['y']-map_box['height']<340
            page.locator('#quick-visit').click();idle()
            assert '1 of 5' in page.locator('#progress-label').inner_text()
            assert page.locator('#quick-visit').evaluate('(e)=>e===document.activeElement')
            assert page.locator('#next-name').inner_text()!=next_name
            page.locator('#quick-undo').click();idle()
            assert '0 of 5' in page.locator('#progress-label').inner_text()
            assert page.locator('#next-name').inner_text()==next_name
            page.locator('#open-journey').click()
            assert page.locator('#journey-details').evaluate('(e)=>e.open')
            page.locator('#stop-list input').first.check();idle()
            assert len(calls)==2
            page.locator('#saved-list button').click();idle()
            assert '1 of 5' in page.locator('#progress-label').inner_text()
            assert len(calls)==2
            assert not errors,errors
            print('PASS: desktop scroll keeps map visible; card keyboard focus; editor regeneration; mobile quick visit/undo/full journey; saved progress/cache; responsive widths.')
        finally:
            if created:
                token=context.request.get(BASE+'/api/session/').json()['csrfToken']
                assert context.request.delete(f'{BASE}/api/adventures/{created}/',headers={'X-CSRFToken':token}).status==204
            context.close();browser.close()


if __name__=='__main__':
    main()
