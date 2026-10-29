import asyncio
import logging

from httpx import AsyncClient, ASGITransport

from echelon_bridge.app import create_app
from echelon_bridge.config import Settings


def test_production_spa_assets_security_headers_and_api_namespace(tmp_path):
    (tmp_path / 'index.html').write_text('<!doctype html><title>Bridge admin</title><div id="app"></div>')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'index-abcdefgh.js').write_text('console.log("bridge")')
    async def run():
        app = create_app(Settings(), frontend_dist=tmp_path)
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url='http://127.0.0.1') as client:
            root = await client.get('/')
            assert root.status_code == 200 and 'Bridge admin' in root.text
            assert root.headers['cache-control'] == 'no-cache'
            assert root.headers['x-content-type-options'] == 'nosniff'
            assert "frame-ancestors 'none'" in root.headers['content-security-policy']
            script = await client.get('/assets/index-abcdefgh.js')
            assert script.status_code == 200 and 'javascript' in script.headers['content-type']
            assert 'immutable' in script.headers['cache-control']
            api = await client.get('/api/metrics')
            legacy = await client.get('/metrics')
            assert api.json() == legacy.json()
            assert api.headers['cache-control'] == 'no-store'
            unknown = await client.get('/api/no-such-route', headers={'accept': 'text/html'})
            assert unknown.status_code == 404 and 'application/json' in unknown.headers['content-type']
            assert unknown.headers['cache-control'] == 'no-store'
            assert (await client.post('/api/metrics', json={'watts': 999})).status_code == 405
            assert (await client.get('/ride', headers={'accept': 'text/html'})).status_code == 200
            assert (await client.get('/ride', headers={'accept': 'application/json'})).status_code == 404
            assert (await client.get('/assets/missing.js', headers={'accept': 'text/html'})).status_code == 404
            assert (await client.get('/.env', headers={'accept': 'text/html'})).status_code == 404
            assert (await client.get('/metrics/missing', headers={'accept': 'text/html'})).status_code == 404
    asyncio.run(run())


def test_missing_build_explains_recovery_while_api_still_works(tmp_path):
    async def run():
        app = create_app(Settings(), frontend_dist=tmp_path / 'absent')
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url='http://localhost') as client:
            root = await client.get('/')
            assert root.status_code == 503 and './bridge build' in root.text
            assert (await client.get('/api/health')).status_code == 200
    asyncio.run(run())


def test_recent_events_are_bounded_redacted_and_handler_is_removed():
    async def run():
        app = create_app(Settings())
        logger = logging.getLogger('echelon_bridge.reader_test')
        parent = logging.getLogger('echelon_bridge')
        original_count = len(parent.handlers)
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url='http://localhost') as client:
            for index in range(110):
                logger.warning('event=connection_retry device=AA:BB:CC:DD:EE:FF attempt=%s', index)
            response = await client.get('/api/events')
            rows = response.json()['events']
            assert len(rows) == 100
            assert all('AA:BB' not in row['message'] for row in rows)
            assert rows[-1]['message'].endswith('attempt=109')
            assert response.headers['cache-control'] == 'no-store'
        assert len(parent.handlers) == original_count
    asyncio.run(run())
