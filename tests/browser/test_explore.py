# Drive the full guest UI in Chrome with mocked tiles and routing, cleaning up test quests.
"""Optional real-browser smoke test against a populated local Docker application.

Requires Playwright only in the test runner's Python environment, not the app.
Uses an isolated guest browser context and removes only adventures it creates.
Run with: python tests/browser/test_explore.py
"""
import os
import base64

from playwright.sync_api import sync_playwright

BASE = os.environ.get('DQ_TEST_URL', 'http://localhost:8000')
CHROME = os.environ.get('DQ_CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME, headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1050})
        # Exercise map interactions without automated pan/zoom traffic to OSM.
        # Actual map imagery and request headers need the separate manual check.
        tile = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1kAAAAASUVORK5CYII=')
        context.route('https://tile.openstreetmap.org/**', lambda route: route.fulfill(status=200, content_type='image/png', body=tile))
        page = context.new_page()
        errors, broken_assets, writes = [], [], []
        routing_calls = []
        routing_mode = {'available': True, 'hold': True, 'error': False}
        pending_routes = []
        result = None
        def fulfill_route(route):
            # Extra vertices verify that legs use provider indices, not stop count.
            source = result['path']['coordinates']
            points = [source[0]]
            for first, second in zip(source, source[1:]):
                points.extend([[(a+b)/2 for a,b in zip(first, second)], second])
            route.fulfill(json={'status':'available','route':{'type':'LineString','coordinates':points},'way_points':list(range(0,len(points),2)), 'distance_m':1608.1,'duration_s':1157.8,
                'notice':'Mock pedestrian estimate; excludes visits. Entrances are not verified.',
                'warnings':[], 'waypoints':[{'displacement_m':1.4}]})
        def route_reply(route):
            routing_calls.append(route.request)
            if routing_mode['hold']:
                pending_routes.append(route); return
            if routing_mode['error']:
                route.abort(); return
            if not routing_mode['available']:
                route.fulfill(json={'status':'unavailable','detail':'Walking routing is not configured. Showing the straight-line exploration sequence.'}); return
            fulfill_route(route)
        page.route('**/api/adventures/*/walking-route/', route_reply)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda response: broken_assets.append(response.url) if '/static/' in response.url and response.status >= 400 else None)
        page.on('request', lambda request: writes.append(request) if '/api/adventures/' in request.url and request.method in ('POST', 'PATCH', 'DELETE') else None)

        def idle():
            page.wait_for_function("!document.querySelector('main').hasAttribute('aria-busy')")

        def click(selector):
            if selector == '#regenerate' and not page.locator(selector).is_visible():
                if not page.locator('#builder').is_visible():
                    page.locator('#map-edit').click()
                selector = '#apply-regenerate'
            page.locator(selector).click()
            idle()

        def search_start():
            page.locator('#place-search').fill('Thomas Moore')
            click('#place-search-form button')
            page.wait_for_selector('#search-results button')
            click('#search-results button >> nth=0')
            assert 'Thomas Moore' in page.locator('#start-label').inner_text()

        response = page.goto(BASE)
        assert response.headers['referrer-policy'] == 'strict-origin-when-cross-origin'
        idle()
        assert page.title() == 'DublinQuest — Explore Dublin Your Way'
        assert page.locator('#generate').is_disabled()
        assert page.locator('.leaflet-control-attribution').is_visible()
        page.wait_for_selector('.leaflet-tile-loaded')  # Mock tiles, not evidence of real OSM imagery.
        created_id = None
        try:
            # Map click, then searchable imported start (no geocoder).
            page.locator('#map').click(position={'x': 200, 'y': 220})
            assert 'Map selection' in page.locator('#start-label').inner_text()
            click('#clear-start')
            assert page.locator('#generate').is_disabled()
            for name, lat, lng in [('Trinity College Dublin',53.3444444444,-6.2577777778),('St Stephen’s Green',53.3380555556,-6.2591666667),('Temple Bar',53.3455875,-6.2627777778)]:
                page.get_by_role('button', name=name, exact=True).click()
                assert name in page.locator('#start-label').inner_text()
                assert f'{lat:.5f}' in page.locator('#start-label').inner_text()
                assert f'{lng:.5f}' in page.locator('#start-label').inner_text()
            page.locator('#place-search').fill('Thomas Moo')
            page.wait_for_selector('#search-results button')
            page.locator('#place-search').press('ArrowDown')
            assert page.locator('#place-search').get_attribute('aria-activedescendant')
            page.locator('#place-search').press('Escape')
            assert page.locator('#search-results button').count() == 0
            page.locator('#place-search').fill('Thomas Moor')
            page.wait_for_selector('#search-results button')
            page.locator('#place-search').press('ArrowDown')
            page.locator('#place-search').press('Enter')
            assert 'Thomas Moore' in page.locator('#start-label').inner_text()
            search_start()
            page.locator('#adventure-title').fill('Browser test — temporary')
            with page.expect_response(lambda response: response.url.endswith('/api/adventures/') and response.request.method == 'POST') as generation:
                click('#generate')
            result = generation.value.json()
            assert generation.value.status == 201, result
            created_id = result['id']
            assert len(result['stops']) == 5
            assert len(result['path']['coordinates']) == 6
            assert len({stop['place']['id'] for stop in result['stops']}) == 5
            assert len({stop['place']['properties']['category'] for stop in result['stops']}) == 4
            page.wait_for_selector('#walking-spinner:not([hidden])')
            assert page.locator('#generate').is_enabled()
            assert page.locator('#stop-list > li').count() == 5
            assert page.locator('#builder').is_hidden()
            page.wait_for_timeout(300)  # Wait for the workspace's Leaflet resize frame.
            map_before = page.locator('#map').bounding_box()
            page.locator('#adventure-section').evaluate('(element) => element.scrollTop = element.scrollHeight')
            map_after = page.locator('#map').bounding_box()
            assert abs(map_before['y'] - map_after['y']) < 5, (map_before,map_after)
            assert map_after['y'] >= 0 and map_after['y'] + map_after['height'] <= 1050
            page.locator('#adventure-section').evaluate('(element) => element.scrollTop = 0')
            assert page.locator('#map path[stroke="#204a3b"]').count() == 1
            assert page.locator('#stop-list input').first.is_enabled()
            routing_mode['hold'] = False
            fulfill_route(pending_routes.pop())
            page.wait_for_selector('#walking-summary:not([hidden])')
            assert page.locator('#map path[stroke="#204a3b"]').count() == 0
            assert page.locator('#walking-summary').is_visible()
            assert '19.3 minutes' in page.locator('#walking-metrics').inner_text()
            assert page.locator('#map .route-leg').count() == 5
            click('#walking-route')
            assert page.locator('#walking-summary').is_hidden()
            assert page.locator('#map path[stroke="#204a3b"]').count() == 1
            click('#walking-route')
            assert len(routing_calls) == 1  # Show/hide reuses the page result.
            click('.leaflet-control-zoom-in')
            click('#fit-map')
            assert len(routing_calls) == 1
            assert page.locator('#stop-list > li').count() == 5
            assert page.locator('.quest-pin:not(.start-pin)').count() == 5
            assert page.locator('#quest-stop-count').inner_text() == '5 discoveries'
            assert page.locator('#next-name').inner_text() == result['stops'][0]['place']['properties']['name']
            assert page.locator('#stop-list .next-stop').count() == 1
            assert page.locator('#stop-list [aria-current="step"]').count() == 1
            assert page.locator('#stop-list .upcoming').count() == 4
            assert page.locator('.next-pin').count() == 1
            assert page.locator('#map .route-leg').count() == 5
            # Popup mutations use the same API and cached route as journey controls.
            click('#stop-list li:first-child .text-button')
            page.wait_for_function("document.querySelectorAll('.popup-visit').length === 1")
            page.locator('.popup-visit').click(); idle()
            assert page.locator('.visited-pin').count() == 1
            assert '✓' in page.locator('.visited-pin').inner_text()
            assert page.locator('#map .route-leg-1.visited-leg').count() == 1
            assert page.locator('#map .route-leg-2.next-leg').count() == 1
            page.wait_for_function("document.querySelectorAll('.popup-visit').length === 1")
            page.locator('.popup-visit').click(); idle()
            assert page.locator('.visited-pin').count() == 0
            assert page.locator('#map .route-leg-1.next-leg').count() == 1
            page.wait_for_function("document.querySelectorAll('.leaflet-popup-close-button').length === 1")
            page.locator('.leaflet-popup-close-button').click()
            assert len(routing_calls) == 1
            # Visiting out of order must not skip the first unchecked stop.
            page.locator('#stop-list input').nth(2).check(); idle()
            assert page.locator('#next-name').inner_text() == result['stops'][0]['place']['properties']['name']
            assert page.locator('#stop-list > li').nth(2).locator('.stop-state span').last.inner_text() == 'Visited'
            assert page.locator('#map .route-leg-3.visited-leg').count() == 1
            assert page.locator('#map .route-leg-1.next-leg').count() == 1
            assert page.locator('.visited-pin').count() == 1
            page.locator('#stop-list input').first.check(); idle()
            assert page.locator('#map .visited-leg').count() == 2
            page.locator('#map-panel').screenshot(path='/tmp/dq-map-progress.png')
            assert page.locator('#map .route-leg-2.next-leg').count() == 1
            page.locator('#stop-list input').first.uncheck(); idle()
            page.locator('#stop-list input').nth(2).uncheck(); idle()
            assert page.locator('#map .visited-leg').count() == 0
            assert len(routing_calls) == 1
            for stop in result['stops']:
                card = page.locator(f'[data-stop-id="{stop["id"]}"]')
                assert card.locator('h3').inner_text() == stop['place']['properties']['name']
                assert card.locator('.stop-number').inner_text() == str(stop['position'])
                # Returned GeoJSON must use Dublin longitude/latitude order.
                lng, lat = stop['place']['geometry']['coordinates']
                assert -6.5 < lng < -6.0 and 53.1 < lat < 53.6
            assert 'not' in page.locator('#sequence-notice').inner_text().lower()
            page.locator('#stop-list li:first-child h3').click()
            assert page.locator('.focused-pin').count() == 1
            click('#stop-list li:first-child .text-button')
            assert page.locator('.leaflet-popup').is_visible()
            page.wait_for_function("document.querySelectorAll('.leaflet-popup-close-button').length === 1")
            page.locator('.leaflet-popup-close-button').click()

            page.locator('#stop-list input').first.check()
            idle()
            assert '1 of 5' in page.locator('#progress-label').inner_text()
            assert page.locator('#next-name').inner_text() == result['stops'][1]['place']['properties']['name']
            assert page.locator('#walking-summary').is_visible()
            assert len(routing_calls) == 1
            page.reload(); idle()
            click('#saved-list button')
            assert '1 of 5' in page.locator('#progress-label').inner_text()
            page.wait_for_selector('#walking-summary:not([hidden])')
            assert len(routing_calls) == 2
            click('#saved-list button')
            assert len(routing_calls) == 2  # Cached reopening does not refetch.
            page.locator('#stop-list input').first.uncheck(); idle()
            assert '0 of 5' in page.locator('#progress-label').inner_text()
            assert page.locator('#next-name').inner_text() == result['stops'][0]['place']['properties']['name']
            click('#next-map')
            assert page.locator('.leaflet-popup').is_visible()
            page.wait_for_function("document.querySelectorAll('.leaflet-popup-close-button').length === 1")
            page.locator('.leaflet-popup-close-button').click()

            click('#edit-quest')
            assert page.locator('#builder').is_visible()
            page.locator('#stop-count').fill('4')
            click('#return-quest')
            assert page.locator('#builder').is_hidden()
            assert page.locator('#stop-count').input_value() == '5'
            click('#edit-quest')
            # All three independent spatial query controls, including pagination.
            click('#nearby')
            assert page.locator('#spatial-list > article').count() > 100
            assert page.locator('#spatial-heading').inner_text() == 'Nearby places'
            all_nearby_count = page.locator('#spatial-list > article').count()
            for checkbox in page.locator('[name=category]').all(): checkbox.uncheck()
            page.locator('[name=category][value=public_art]').check()
            page.locator('#radius').select_option('500')
            click('#nearby')
            assert 0 < page.locator('#spatial-list > article').count() < all_nearby_count
            assert all('Public art' in card.inner_text() for card in page.locator('#spatial-list > article').all())
            page.locator('#radius').select_option('2000')
            for checkbox in page.locator('[name=category]').all(): checkbox.check()
            assert page.locator('#spatial-section').is_hidden()  # Radius change clears stale results.
            click('#intersections')
            assert page.locator('#spatial-list > article').count() > 0
            assert 'Parks overlapping' in page.locator('#spatial-heading').inner_text()
            page.locator('#park-search').fill('Merrion')
            click('#park-search-form button')
            click('#park-results button >> nth=0')
            assert 'Inside' in page.locator('#spatial-heading').inner_text()
            assert page.locator('#spatial-list > article').count() > 0

            # Empty and error feedback keep the current saved adventure intact.
            page.locator('#place-search').fill('zzzznotarealplace')
            click('#place-search-form button')
            page.wait_for_function("document.querySelector('#search-status').textContent.includes('No imported matches')")
            assert 'No matching places' in page.locator('#feedback').inner_text()
            for checkbox in page.locator('[name=category]').all(): checkbox.uncheck()
            click('#generate')
            assert 'at least one category' in page.locator('#feedback').inner_text()
            for checkbox in page.locator('[name=category]').all(): checkbox.check()
            # Force a demonstrated API validation error without changing backend rules.
            page.locator('#adventure-title').evaluate('(element) => element.value = "X".repeat(121)')
            page.locator('#adventure-form').evaluate('(form) => form.dispatchEvent(new Event("submit", {cancelable:true}))')
            idle()
            assert page.locator('#feedback').evaluate('(element) => element.classList.contains("error")')
            page.locator('#adventure-title').fill('Browser test — temporary')
            click('#refresh-saved')

            # Responsive layouts have no horizontal page overflow.
            for width, height, name in [(1440, 1050, 'desktop'), (820, 1180, 'tablet'), (390, 844, 'mobile')]:
                page.set_viewport_size({'width': width, 'height': height})
                page.wait_for_timeout(250)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name
                assert page.locator('#generate').is_visible()
                assert page.locator('#map').evaluate('(element) => element.getBoundingClientRect().height') >= 240
                page.screenshot(path=f'/tmp/dublinquest-{name}.png', full_page=True)
            page.set_viewport_size({'width': 1440, 'height': 1050})
            # Actual session isolation and CSRF rejection from separate browser context.
            other = browser.new_context()
            assert other.request.get(f'{BASE}/api/adventures/{created_id}/').status == 404
            assert other.request.get(f'{BASE}/api/adventures/').json()['count'] == 0
            other.close()
            assert context.request.delete(f'{BASE}/api/adventures/{created_id}/').status == 403

            # Regenerate with changed settings, preserving UUID and clearing visits.
            routing_mode['available'] = False
            page.locator('#stop-count').fill('3')
            page.once('dialog', lambda dialog: dialog.accept())
            click('#regenerate')
            assert page.locator('#stop-list > li').count() == 3
            assert page.locator('#builder').is_hidden()
            assert page.locator('#quest-stop-count').inner_text() == '3 discoveries'
            assert '0 of 3' in page.locator('#progress-label').inner_text()
            assert page.locator('#walking-summary').is_hidden()
            assert page.locator('#map .route-leg').count() == 0
            page.wait_for_function("document.querySelector('#walking-status').textContent.includes('not configured')")
            assert page.locator('#map path[stroke="#204a3b"]').count() == 1
            assert len(routing_calls) == 3
            click('#saved-list button')
            assert len(routing_calls) == 3
            routing_mode['hold'] = True
            page.once('dialog', lambda dialog: dialog.accept())
            click('#regenerate')
            page.wait_for_selector('#walking-spinner:not([hidden])')
            assert page.locator('#regenerate').is_enabled()
            routing_mode['hold'] = False
            routing_mode['error'] = True
            page.once('dialog', lambda dialog: dialog.accept())
            click('#regenerate')
            page.wait_for_function("document.querySelector('#walking-status').textContent.includes('Unable to reach')")
            assert page.locator('#map path[stroke="#204a3b"]').count() == 1
            assert len(routing_calls) == 5
            fulfill_route(pending_routes.pop())  # A late route from the previous generation must be ignored.
            page.wait_for_timeout(150)
            assert page.locator('#walking-summary').is_hidden()
            assert 'Unable to reach' in page.locator('#walking-status').inner_text()
            assert page.locator('#stop-list > li').count() == 3
            page.once('dialog', lambda dialog: dialog.accept('Renamed browser adventure'))
            click('#rename')
            assert page.locator('#adventure-heading').inner_text() == 'Renamed browser adventure'
            for checkbox in page.locator('#stop-list input').all():
                checkbox.check(); idle()
            assert page.locator('#completion').is_visible()
            assert page.locator('#next-discovery').is_hidden()
            assert page.locator('#stop-list .visited').count() == 3
            assert page.locator('#stop-list [aria-current="step"]').count() == 0
            page.locator('#stop-list input').first.uncheck(); idle()
            assert page.locator('#completion').is_hidden()
            assert page.locator('#next-discovery').is_visible()
            assert page.locator('#stop-list > li').first.get_attribute('aria-current') == 'step'
            page.locator('#stop-list input').first.check(); idle()
            assert page.locator('#completion').is_visible()
            assert len(routing_calls) == 5
            # Show a server/network failure without losing the adventure.
            page.route('**/api/adventures/?*', lambda route: route.abort())
            page.route('**/api/adventures/', lambda route: route.abort())
            click('#refresh-saved')
            assert 'Unable to reach' in page.locator('#feedback').inner_text()
            page.unroute('**/api/adventures/?*'); page.unroute('**/api/adventures/')
            assert writes and all(request.headers.get('x-csrftoken') for request in writes)
            assert not errors, errors
            assert not broken_assets, broken_assets
            page.once('dialog', lambda dialog: dialog.accept())
            click('#delete-adventure')
            assert page.locator('#adventure-section').is_hidden()
            assert context.request.get(f'{BASE}/api/adventures/{created_id}/').status == 404
            created_id = None
            print('PASS: map/search, generation, cards/markers, three spatial controls, progress, reload, guest/CSRF, validation, responsive layouts, regeneration, rename, completion, deletion; no JS errors or failed static assets.')
        finally:
            if created_id:
                token = context.request.get(f'{BASE}/api/session/').json()['csrfToken']
                context.request.delete(f'{BASE}/api/adventures/{created_id}/', headers={'X-CSRFToken': token, 'Referer': BASE + '/'})
            context.close(); browser.close()


if __name__ == '__main__':
    main()
