import asyncio
import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp.test_utils import TestServer, TestClient
from server import create_app

class Signaling(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.app=create_app(relay=False)
  self.client=TestClient(TestServer(self.app));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close()
 async def room(self):
  r=await self.client.post('/call/api/rooms',json={'mode':'audio'});self.assertEqual(r.status,201);return await r.json()
 async def test_auth_capacity_generation_and_end(self):
  r=await self.room();host={'room':r['room'],'token':r['token']};guest={'room':r['room'],'token':r['invite']}
  bad=await self.client.post('/call/api/info',json={'room':r['room'],'token':'wrong'});self.assertEqual(bad.status,403)
  a=await self.client.ws_connect('/call/ws');await a.send_json(host);self.assertEqual((await a.receive_json())['role'],'host')
  duplicate=await self.client.ws_connect('/call/ws');await duplicate.send_json(host);self.assertEqual((await duplicate.receive_json())['type'],'error');await duplicate.close()
  b=await self.client.ws_connect('/call/ws');await b.send_json(guest);self.assertEqual((await b.receive_json())['role'],'guest')
  self.assertEqual((await a.receive_json())['type'],'peer');ready=await a.receive_json();self.assertEqual(ready['type'],'ready');self.assertEqual(await b.receive_json(),ready)
  await a.send_json({'type':'offer','generation':ready['generation'],'description':{'type':'offer','sdp':'example'}})
  self.assertEqual((await b.receive_json())['type'],'offer')
  # A guest cannot spoof a host offer, and old-generation candidates are discarded.
  await b.send_json({'type':'offer','generation':ready['generation'],'description':{}})
  await b.send_json({'type':'candidate','generation':0,'candidate':{}})
  await b.send_json({'type':'media','mic':False,'camera':False,'token':'must-not-forward'})
  data=await a.receive_json();self.assertEqual(data['type'],'media');self.assertNotIn('token',data)
  await b.close();self.assertEqual((await a.receive_json())['type'],'peer-left')
  b=await self.client.ws_connect('/call/ws');await b.send_json(guest);await b.receive_json();await a.receive_json();new=await a.receive_json();self.assertGreater(new['generation'],ready['generation']);await b.receive_json()
  await a.send_json({'type':'end'});self.assertEqual((await b.receive_json())['type'],'ended');self.assertEqual((await a.receive_json())['type'],'ended');await a.close();await b.close()
  gone=await self.client.post('/call/api/info',json=guest);self.assertEqual(gone.status,410)
 async def test_expiry_origin_limits_and_static(self):
  r=await self.room();self.app['service'].rooms[r['room']].expires=time.time()-1
  expired=await self.client.post('/call/api/info',json={'room':r['room'],'token':r['invite']});self.assertEqual(expired.status,410)
  forbidden=await self.client.post('/call/api/rooms',json={},headers={'Origin':'https://evil.example'});self.assertEqual(forbidden.status,403)
  allowed=await self.client.options('/call/api/rooms',headers={'Origin':'https://app.bomalo.ir'});self.assertEqual(allowed.headers['Access-Control-Allow-Origin'],'https://app.bomalo.ir')
  for _ in range(14):await self.room()
  limited=await self.client.post('/call/api/rooms',json={});self.assertEqual(limited.status,429)
  self.assertEqual((await self.client.get('/call/')).status,200)
  self.assertEqual((await self.client.get('/call/app.js')).status,200)
  self.assertEqual((await self.client.get('/call/../server.py')).status,404)

if __name__=='__main__':unittest.main()
