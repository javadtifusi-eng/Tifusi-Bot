"""Panel truth, quota carry-over, and safe completion of paid operations."""
import asyncio
import datetime
import json
import time
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import bot
import miniapp
from tests.conftest import customer
from tests.test_miniapp import _h, TOKEN

REAL_CREATE = bot.create_service_on_panel
GB = 1024 ** 3


def order(**extra):
    return dict(id=1, username='alice', protocol='xray', expire_at=int(time.time())+30*86400,
                volume_gb=30, sub_url='https://sub.example/sub/stable', status='active', **extra)


def panel_user(**extra):
    return dict(id=2, username='alice', secret='test-secret', status='active',
                data_limit=50*GB, used_traffic=20*GB, **extra)


def test_customer_uses_panel_expiry(world):
    u=panel_user();u['expire']='2030-01-01T00:00:00Z'
    result=miniapp._customer(order(),u)
    assert result['expire']==1893456000


@pytest.mark.parametrize('limit',[None,0])
def test_customer_honors_panel_unlimited(world,limit):
    u=panel_user();u.update(data_limit=limit,expire=None)
    result=miniapp._customer(order(),u)
    assert result['limit']==0 and result['expire'] is None and result['days_left'] is None


def test_customer_missing_panel_fields_falls_back(world):
    result=miniapp._customer(order(),{})
    assert result['limit']==30*GB and result['expire']==order()['expire_at']


def test_customer_bad_panel_date_falls_back(world):
    u=panel_user();u['expire']='not-a-date'
    assert miniapp._customer(order(),u)['expire']==order()['expire_at']


def test_customer_disabled_is_not_healthy(world):
    u=panel_user();u['status']='disabled'
    result=miniapp._customer(order(),u)
    assert result['on'] is False and result['state']!='ok'


@pytest.mark.parametrize('used,limit,new_gb,remaining',[(20,50,30,60),(65,50,30,30),(50,50,30,30),(20,50,0,None)])
def test_renew_carries_volume_and_keeps_identity(world,monkeypatch,used,limit,new_gb,remaining):
    client=bot.TifusiPanelAPI('https://panel.example','admin','fake')
    u=panel_user();u.update(used_traffic=used*GB,data_limit=limit*GB,protocols=['vless','l2tp'])
    monkeypatch.setattr(client,'find_user',lambda name:dict(u))
    writes=[]
    def call(path,method='get',**kw):
        if method=='put':
            writes.append(kw['json']);u.update(kw['json']);return dict(u)
        return {'subscription_url':'https://sub.example/sub/stable','app_code':'same'}
    monkeypatch.setattr(client,'_call',call)
    r=client.renew_user('alice',new_gb,1893456000,protocols=['vless'])
    assert r['user']['id']==2 and r['subscription_url'].endswith('/stable')
    assert r['user']['used_traffic']==used*GB and writes[0]['status']=='active'
    assert writes[0]['protocols']==['vless','l2tp']
    if remaining is None:assert r['user']['data_limit'] is None
    else:assert r['user']['data_limit']-used*GB==remaining*GB


def test_renew_extends_actual_panel_date(world,monkeypatch):
    client=bot.TifusiPanelAPI('https://panel.example','admin','fake')
    u=panel_user();u['expire']='2030-01-01T00:00:00Z'
    monkeypatch.setattr(client,'find_user',lambda name:dict(u))
    writes=[]
    def call(path,method='get',**kw):
        if method=='put':writes.append(kw['json']);return dict(u,**kw['json'])
        return {'subscription_url':'https://sub.example/sub/stable'}
    monkeypatch.setattr(client,'_call',call)
    client.renew_user('alice',30,int(time.time())+30*86400,renewal_days=30)
    assert int(datetime.datetime.fromisoformat(writes[0]['expire']).timestamp())==1893456000+30*86400


def test_committed_user_survives_links_endpoint_failure(world,monkeypatch):
    client=bot.TifusiPanelAPI('https://panel.example','admin','fake')
    def fail(*a,**kw):raise bot.PanelError('links unavailable')
    monkeypatch.setattr(client,'_call',fail)
    result=client._with_links(panel_user(),committed=True)
    assert result['subscription_url']=='https://panel.example/sub/test-secret'
    assert result['links_pending'] is True


def test_pending_purchase_concurrent_resume_counts_once(world,plan,monkeypatch):
    uid=customer(9991,balance=600_000)
    bot.db.set_setting(miniapp.PENDING_KEY.format(uid),json.dumps({'service':'xray','plan_id':plan['id'],'qty':1,'username':'pending','saved_at':time.time()}))
    calls=[]
    async def run():
        started=asyncio.Event();release=asyncio.Event()
        lock=miniapp._buy_locks.setdefault(uid,asyncio.Lock())
        await lock.acquire()
        async def create(*a,**kw):
            calls.append(1);started.set();await release.wait()
            return [{'id':1,'username':'pending'}],None
        monkeypatch.setattr(miniapp,'_create_accounts',create)
        first=asyncio.create_task(miniapp.resume_pending_buy(world.app.bot,uid))
        await asyncio.sleep(0)
        second=asyncio.create_task(miniapp.resume_pending_buy(world.app.bot,uid))
        await asyncio.sleep(0)
        lock.release()
        await started.wait()
        release.set()
        await asyncio.gather(first,second)
    asyncio.run(run())
    assert len(calls)==1


@pytest.mark.parametrize('body',[[],{'order_id':'oops'},{'order_id':1,'plan_id':'oops'}])
def test_renew_malformed_input_never_500(world,monkeypatch,body):
    uid=customer(9992,balance=300_000)
    monkeypatch.setitem(miniapp.ns,'BOT_TOKEN',TOKEN)
    async def go():
        app=web.Application(middlewares=[miniapp.auth_mw]);app['tg_app']=world.app
        app.router.add_post('/api/renew',miniapp.api_renew)
        async with TestClient(TestServer(app)) as client:
            r=await client.post('/api/renew',json=body,headers=_h(uid))
            return r.status
    assert asyncio.run(go()) in (400,404)
    assert bot.db.get_balance(uid)==300_000


def install_panel(monkeypatch):
    pid=bot.db.add_panel({'name':'test','url':'https://panel.example','username':'admin','password':'fake','protocols':{'vless':1}})
    p=bot.db.get_panel(pid)
    client=bot.TifusiPanelAPI(p['url'],'admin','fake')
    monkeypatch.setattr(bot,'panel_client',lambda p:client)
    monkeypatch.setattr(bot,'pick_panel',lambda *a:p)
    monkeypatch.setitem(miniapp.ns,'panel_client',bot.panel_client)
    monkeypatch.setitem(miniapp.ns,'pick_panel',bot.pick_panel)
    monkeypatch.setitem(miniapp.ns,'BOT_TOKEN',TOKEN)
    return p,client


def request_api(world,path,uid,payload):
    async def go():
        app=web.Application(middlewares=[miniapp.auth_mw]);app['tg_app']=world.app
        app.router.add_post('/api/renew',miniapp.api_renew)
        app.router.add_post('/api/buy',miniapp.api_buy)
        app.router.add_post('/api/toggle',miniapp.api_toggle)
        async with TestClient(TestServer(app)) as client:
            r=await client.post(path,json=payload,headers=_h(uid))
            return r.status,await r.json()
    return asyncio.run(go())


@pytest.mark.parametrize('link_failure',[False,True])
def test_wallet_renew_full_flow_keeps_money_quota_and_panel_date(world,plan,monkeypatch,link_failure):
    uid=customer(9995,balance=500_000)
    p,client=install_panel(monkeypatch)
    oid=bot.db.create_order(dict(user_id=uid,panel_id=p['id'],plan_id=plan['id'],protocol='xray',username='alice',
                                expire_at=int(time.time())+86400,volume_gb=50,sub_url='https://sub.example/sub/stable',app_code='same'))
    u=panel_user();u.update(expire='2030-01-01T00:00:00Z',protocols=['vless'])
    monkeypatch.setattr(client,'find_user',lambda name:dict(u))
    writes=[]
    def call(path,method='get',**kw):
        if method=='put':writes.append(kw['json']);u.update(kw['json']);return dict(u)
        if link_failure:raise bot.PanelError('links unavailable')
        return {'subscription_url':'https://sub.example/sub/stable','app_code':'same'}
    monkeypatch.setattr(client,'_call',call)
    miniapp._panel_cache[p['id']]=(time.time(),{'alice':dict(u)})
    status,body=request_api(world,'/api/renew',uid,{'order_id':oid,'plan_id':plan['id']})
    assert status==200 and body['ok'] and len(writes)==1
    assert bot.db.get_balance(uid)==300_000
    stored=bot.db.get_order(oid)
    assert stored['expire_at']==body['expire']==1893456000+30*86400
    assert stored['sub_url']=='https://sub.example/sub/stable' and stored['app_code']=='same'
    assert u['data_limit']-u['used_traffic']==60*GB
    assert p['id'] not in miniapp._panel_cache


@pytest.mark.parametrize('balance,owner,failed,expected',[(100_000,True,False,402),(500_000,False,False,404),(500_000,True,True,502)])
def test_wallet_renew_failures_never_take_money(world,plan,monkeypatch,balance,owner,failed,expected):
    uid=customer(9996,balance=balance)
    p,client=install_panel(monkeypatch)
    oid=bot.db.create_order(dict(user_id=uid if owner else 9997,panel_id=p['id'],plan_id=plan['id'],protocol='xray',username='alice',expire_at=0))
    writes=[]
    def find(name):
        writes.append('read')
        if failed:raise bot.PanelError('panel unavailable before write')
        return panel_user()
    monkeypatch.setattr(client,'find_user',find)
    status,body=request_api(world,'/api/renew',uid,{'order_id':oid,'plan_id':plan['id']})
    assert status==expected and bot.db.get_balance(uid)==balance
    if not failed:assert writes==[]


def test_toggle_uses_panel_expiry_after_admin_extension(world,plan,monkeypatch):
    uid=customer(9998)
    p,client=install_panel(monkeypatch)
    oid=bot.db.create_order(dict(user_id=uid,panel_id=p['id'],plan_id=plan['id'],protocol='xray',username='alice',expire_at=1))
    u=panel_user();u['expire']='2030-01-01T00:00:00Z'
    monkeypatch.setattr(miniapp,'_panel_users',lambda panel:{'alice':u})
    calls=[]
    monkeypatch.setattr(client,'set_status',lambda *a:calls.append(a) or True)
    status,body=request_api(world,'/api/toggle',uid,{'order_id':oid,'on':True})
    assert status==200 and calls==[('alice','active')]


def test_links_read_failure_without_committed_write_still_raises(world,monkeypatch):
    client=bot.TifusiPanelAPI('https://panel.example','admin','fake')
    def fail(*a,**kw):raise bot.PanelError('unavailable')
    monkeypatch.setattr(client,'_call',fail)
    with pytest.raises(bot.PanelError):client._with_links(panel_user())


def test_buy_committed_account_not_refunded_when_links_fail(world,plan,monkeypatch):
    uid=customer(9999,balance=500_000)
    p,client=install_panel(monkeypatch)
    bot.db.set_service_map(p['id'],{'xray':{'id':0,'name':'public'}})
    created=[]
    monkeypatch.setattr(client,'find_user',lambda name:None)
    def call(path,method='get',**kw):
        if method=='post':
            created.append(kw['json'])
            return dict(kw['json'],id=77,secret='new-secret',used_traffic=0)
        raise bot.PanelError('links temporarily unavailable after save')
    monkeypatch.setattr(client,'_call',call)
    monkeypatch.setitem(miniapp.ns,'create_service_on_panel',REAL_CREATE)
    status,body=request_api(world,'/api/buy',uid,{'service':'xray','plan_id':plan['id'],'username':'newcust'})
    assert status==200 and body['ok'] and len(created)==1
    assert bot.db.get_balance(uid)==300_000 and len(body['made'])==1
    saved=bot.db.get_order(body['made'][0]['id'])
    assert saved['sub_url']=='https://panel.example/sub/new-secret'
    assert saved['status']=='active' and saved['price']==200_000


@pytest.mark.parametrize('value,expected',[('2030-01-01T00:00:00Z',1893456000),('2030-01-01T03:30:00+03:30',1893456000),('2030-01-01T00:00:00',1893456000),(None,0)])
def test_panel_expiry_timestamp_formats(value,expected):
    assert bot.panel_expire_ts(value)==expected
