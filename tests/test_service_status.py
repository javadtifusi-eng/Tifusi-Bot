"""Public links reveal only one order's read-only statistics; admin APIs stay signed."""
import asyncio
import time
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest
import miniapp


@pytest.fixture
def service(monkeypatch):
    order = dict(id=7, user_id=100, panel_id=1, username='client', protocol='xray',
                 sub_url='https://sub.example/PRIVATE', status='active', expire_at=int(time.time())+86400,
                 volume_gb=10, password='NEVER-PUBLIC')
    pu = dict(username='client', status='active', used_traffic=1073741824, data_limit=10737418240,
              last_seen='2026-10-28T10:20:00Z', password='NEVER-PUBLIC', subscription_url=order['sub_url'])
    db = SimpleNamespace(get_order=lambda oid: order if oid == 7 else None,
                         get_panel=lambda pid: {'id':1})
    for key, value in dict(db=db, BOT_TOKEN='test-key', public_sub_url=lambda x:x,
                           service_name=lambda x:x).items():
        monkeypatch.setitem(miniapp.ns,key,value)
    monkeypatch.setattr(miniapp, '_panel_users', lambda p: {'client':pu})
    return order, pu


def run(service, test):
    async def go():
        app=web.Application(middlewares=[miniapp.auth_mw])
        app.router.add_get('/service/{order_id}/{signature}',miniapp.service_status_page)
        app.router.add_get('/service/{order_id}/{signature}/data',miniapp.service_status_data)
        app.router.add_get('/api/connect',miniapp.api_connect)
        async with TestClient(TestServer(app)) as c:
            return await test(c,'/service/7/'+miniapp._status_signature(service[0]))
    return asyncio.run(go())


def test_scoped_link_and_no_secrets(service):
    async def check(c,url):
        page=await c.get(url)
        assert page.status==200 and page.headers['Cache-Control']=='no-store'
        assert "frame-ancestors 'none'" in page.headers['Content-Security-Policy']
        assert "font-src 'self'" in page.headers['Content-Security-Policy']
        r=await c.get(url+'/data'); d=await r.json()
        assert r.status==200 and d['used']==1073741824 and d['days_left']==1
        assert d['last_seen']==1793182800
        assert 'NEVER-PUBLIC' not in str(d) and 'PRIVATE' not in str(d)
        assert set(d)=={'username','service_name','used','limit','expire','days_left','panel_status','last_seen','updated_at'}
        assert (await c.get(url.replace('/7/','/8/')+'/data')).status==404
        assert (await c.get(url[:-1]+('a' if url[-1]!='a' else 'b')+'/data')).status==404
        assert (await c.get('/service/7/ناقص/data')).status==404
        assert (await c.get('/api/connect?order_id=7')).status==401
        service[0]['sub_url']='https://sub.example/replaced'
        assert (await c.get(url+'/data')).status==404
    run(service,check)


def test_removed_order_revokes_link(service):
    async def check(c,url):
        service[0]['status']='deleted'
        assert (await c.get(url)).status==404
        assert (await c.get(url+'/data')).status==404
    run(service,check)


def test_panel_outage_never_shows_zero_usage(service,monkeypatch):
    def failed(_): raise RuntimeError('private internal failure')
    monkeypatch.setattr(miniapp,'_panel_users',failed)
    async def check(c,url):
        r=await c.get(url+'/data'); d=await r.json()
        assert r.status==503 and d=={'error':'unavailable'}
    run(service,check)


def test_unlimited_disabled_and_missing_last_seen(service,monkeypatch):
    service[1].update(data_limit=0,expire=None,status='disabled',last_seen=None)
    monkeypatch.setitem(miniapp.ns,'panel_expire_ts',lambda v: 0)
    async def check(c,url):
        r=await c.get(url+'/data'); d=await r.json()
        assert r.status==200 and d['limit']==0 and d['days_left'] is None
        assert d['last_seen'] is None and d['panel_status']=='disabled'
    run(service,check)


def test_only_order_owner_receives_link(service,monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    async def connection(*a,**kw): return {"id":7}
    monkeypatch.setattr(miniapp,'_order_connect',connection)
    async def go():
        r=make_mocked_request('GET','/api/connect?order_id=7');r['uid']=100
        response=await miniapp.api_connect(r)
        import json
        assert json.loads(response.text)['status_url'].endswith(miniapp._status_signature(service[0]))
        r['uid']=101
        assert (await miniapp.api_connect(r)).status==404
    asyncio.run(go())
