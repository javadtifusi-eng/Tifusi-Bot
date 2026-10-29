"""Two-person room signaling. Media stays in WebRTC; no recording or accounts."""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import signal
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from aiohttp import web, WSMsgType

ROOT = Path(__file__).parent
ORIGINS = {'https://app.bomalo.ir', 'https://tifusi-call-javad.stablejay11.chatgpt.site'}
ROOM_TTL = 3600
MAX_ROOMS = 100
TURN_IP = os.environ.get('CALL_TURN_IP', '167.233.64.15')
TURN_PORT = int(os.environ.get('CALL_TURN_PORT', '3478'))

@dataclass
class Room:
    id: str
    host: str
    guest: str
    expires: float
    mode: str
    peers: dict = field(default_factory=dict)
    generation: int = 0
    last_active: float = field(default_factory=time.time)

class Service:
    def __init__(self, relay=True):
        self.rooms = {}
        self.rates = defaultdict(deque)
        self.secret = secrets.token_urlsafe(48)
        self.relay = relay
        self.turn = None
        self.turn_fd = None

    def check_rate(self, key, limit, window):
        now = time.monotonic()
        queue = self.rates[key]
        while queue and queue[0] < now-window:
            queue.popleft()
        if len(queue) >= limit:
            raise web.HTTPTooManyRequests(text='کمی صبر کن و دوباره امتحان کن.')
        queue.append(now)

    def auth(self, data):
        room = self.rooms.get(str(data.get('room', '')))
        if not room or time.time() >= room.expires:
            raise web.HTTPGone(text='این اتاق بسته شده یا اعتبار لینک تمام شده.')
        token = str(data.get('token', ''))
        if secrets.compare_digest(token, room.host):
            return room, 'host'
        if secrets.compare_digest(token, room.guest):
            return room, 'guest'
        raise web.HTTPForbidden(text='لینک دعوت معتبر نیست.')

    def ice(self, room, role):
        username = f'{int(room.expires)+600}:{room.id}:{role}'
        credential = base64.b64encode(hmac.new(self.secret.encode(), username.encode(), hashlib.sha1).digest()).decode()
        if not self.relay:
            return []
        return [{'urls': [f'stun:{TURN_IP}:{TURN_PORT}']}, {'urls': [f'turn:{TURN_IP}:{TURN_PORT}?transport=udp', f'turn:{TURN_IP}:{TURN_PORT}?transport=tcp'], 'username': username, 'credential': credential}]

    async def broadcast(self, room, data, exclude=None):
        for role, ws in list(room.peers.items()):
            if role != exclude and not ws.closed:
                try:
                    await ws.send_json(data)
                except (ConnectionError, RuntimeError):
                    pass

    async def end(self, room, reason='ended'):
        self.rooms.pop(room.id, None)
        await self.broadcast(room, {'type': 'ended', 'reason': reason})
        for ws in list(room.peers.values()):
            await ws.close(code=1000)

    async def cleanup(self, app):
        async def collect():
            while True:
                await asyncio.sleep(15)
                now = time.time()
                for room in list(self.rooms.values()):
                    if room.expires <= now or (not room.peers and now-room.last_active > 120):
                        await self.end(room, 'expired')
                for key, values in list(self.rates.items()):
                    if not values or values[-1] < time.monotonic()-3600:
                        self.rates.pop(key, None)
        task = asyncio.create_task(collect())
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for room in list(self.rooms.values()):
            await self.end(room, 'restart')

    async def turn_context(self, app):
        if not self.relay:
            yield
            return
        # Anonymous in-memory fd: no shared credential is written to disk or argv.
        config = f'''listening-port={TURN_PORT}
listening-ip={TURN_IP}
relay-ip={TURN_IP}
min-port=49160
max-port=49259
fingerprint
use-auth-secret
static-auth-secret={self.secret}
realm=tifusi-call
no-tls
no-dtls
no-cli
no-tcp-relay
no-multicast-peers
user-quota=8
total-quota=200
max-bps=1000000
bps-capacity=15000000
stale-nonce=600
log-file=stdout
simple-log
no-stdout-log
pidfile=/tmp/tifusi-call-turn.pid
'''
        # Never allow relay access to internal/metadata addresses or this host's services.
        for network in ['0.0.0.0-0.255.255.255','10.0.0.0-10.255.255.255','100.64.0.0-100.127.255.255','127.0.0.0-127.255.255.255','169.254.0.0-169.254.255.255','172.16.0.0-172.31.255.255','192.168.0.0-192.168.255.255','224.0.0.0-255.255.255.255','167.233.68.133']:
            config += f'denied-peer-ip={network}\n'
        # Same-host relay candidates are required for two users behind restrictive NAT.
        # Bind to public IPv4 and use two relay threads on this small host.
        config += 'relay-threads=2\n'
        self.turn_fd = os.memfd_create('call-turn', flags=0)
        os.write(self.turn_fd, config.encode())
        os.lseek(self.turn_fd, 0, 0)
        self.turn = await asyncio.create_subprocess_exec('/usr/bin/turnserver', '-c', f'/proc/self/fd/{self.turn_fd}', pass_fds=(self.turn_fd,), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await asyncio.sleep(.7)
        if self.turn.returncode is not None:
            raise RuntimeError('TURN could not start')
        async def monitor():
            await self.turn.wait()
            # Restart the signaling process and relay together after an unexpected exit.
            os.kill(os.getpid(), signal.SIGTERM)
        watch = asyncio.create_task(monitor())
        yield
        watch.cancel()
        if self.turn.returncode is None:
            self.turn.terminate()
            await self.turn.wait()
        os.close(self.turn_fd)


def create_app(relay=True):
    service = Service(relay)
    @web.middleware
    async def boundary(request, handler):
        origin = request.headers.get('Origin')
        if origin and origin not in ORIGINS:
            raise web.HTTPForbidden(text='Origin not allowed')
        if request.method == 'OPTIONS':
            response = web.Response(status=204)
        else:
            try:
                response = await handler(request)
            except web.HTTPException as e:
                response = e
        if not response.prepared:
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            if origin in ORIGINS:
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Vary'] = 'Origin'
                response.headers['Access-Control-Allow-Methods'] = 'POST,GET,OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Permissions-Policy'] = 'camera=(self), microphone=(self), geolocation=()'
        return response
    app = web.Application(client_max_size=160*1024, middlewares=[boundary])
    app['service'] = service
    def ip(request):
        # Proxy only binds loopback and Caddy supplies this header.
        return request.headers.get('X-Forwarded-For', request.remote or '').split(',')[0].strip()
    async def create(request):
        service.check_rate(('create', ip(request)), 15, 3600)
        if len(service.rooms) >= MAX_ROOMS:
            raise web.HTTPServiceUnavailable(text='ظرفیت تماس‌ها پر شده؛ کمی بعد امتحان کن.')
        data = await request.json()
        mode = data.get('mode', 'video')
        if mode not in ('audio', 'video'):
            raise web.HTTPBadRequest()
        room = Room(secrets.token_urlsafe(18), secrets.token_urlsafe(32), secrets.token_urlsafe(32), time.time()+ROOM_TTL, mode)
        service.rooms[room.id] = room
        return web.json_response({'room': room.id, 'token': room.host, 'invite': room.guest, 'expires': room.expires, 'mode': mode}, status=201)
    async def info(request):
        room, role = service.auth(await request.json())
        return web.json_response({'mode': room.mode, 'expires': room.expires, 'role': role, 'iceServers': service.ice(room, role)})
    async def end(request):
        room, _ = service.auth(await request.json())
        await service.end(room)
        return web.json_response({'ok': True})
    async def health(request):
        ready = not service.relay or (service.turn and service.turn.returncode is None)
        return web.json_response({'ok': bool(ready), 'relay': bool(service.relay)}, status=200 if ready else 503)
    async def ws_handler(request):
        service.check_rate(('ws', ip(request)), 120, 60)
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=128*1024)
        await ws.prepare(request)
        room = None
        role = None
        try:
            first = await ws.receive_json(timeout=10)
            room, role = service.auth(first)
            old = room.peers.get(role)
            if old is not None and not old.closed:
                await ws.send_json({'type': 'error', 'message': 'این لینک همین حالا روی دستگاه دیگری باز است.'})
                await ws.close(code=4009)
                return ws
            name = str(first.get('name', 'دوستت'))[:40].strip() or 'دوستت'
            room.peers[role] = ws
            room.last_active = time.time()
            await ws.send_json({'type': 'joined', 'role': role, 'name': name, 'expires': room.expires})
            await service.broadcast(room, {'type': 'peer', 'name': name}, exclude=role)
            if len(room.peers) == 2:
                room.generation += 1
                await service.broadcast(room, {'type': 'ready', 'generation': room.generation})
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                service.check_rate(('signal', room.id, role), 500, 60)
                try:
                    data = json.loads(msg.data)
                except (ValueError, TypeError):
                    await ws.close(code=1008)
                    break
                if not isinstance(data, dict):
                    break
                kind = data.get('type')
                if kind == 'end':
                    await service.end(room)
                    break
                if kind not in ('offer', 'answer', 'candidate', 'media', 'restart'):
                    continue
                if kind in ('offer', 'answer', 'candidate') and data.get('generation') != room.generation:
                    continue
                if kind == 'offer' and role != 'host' or kind == 'answer' and role != 'guest':
                    continue
                if kind == 'media':
                    data = {'type': 'media', 'mic': bool(data.get('mic')), 'camera': bool(data.get('camera')), 'name': name}
                await service.broadcast(room, data, exclude=role)
        except web.HTTPException as e:
            await ws.send_json({'type': 'error', 'message': e.text})
        except (asyncio.TimeoutError, ValueError, TypeError):
            if not ws.closed:
                await ws.send_json({'type': 'error', 'message': 'اتصال معتبر نیست؛ دوباره وارد شو.'})
        finally:
            if room and room.peers.get(role) is ws:
                room.peers.pop(role, None)
                room.last_active = time.time()
                await service.broadcast(room, {'type': 'peer-left'})
            await ws.close()
        return ws
    async def index(request):
        return web.FileResponse(ROOT/'dist/index.html')
    async def redirect(request):
        raise web.HTTPFound('/call/')
    app.router.add_get('/call', redirect)
    app.router.add_get('/call/', index)
    app.router.add_get('/call/health', health)
    app.router.add_post('/call/api/rooms', create)
    app.router.add_post('/call/api/info', info)
    app.router.add_post('/call/api/end', end)
    app.router.add_get('/call/ws', ws_handler)
    async def options(request):
        return web.Response(status=204)
    app.router.add_route('OPTIONS', '/call/{path:.*}', options)
    app.router.add_static('/call/', ROOT/'dist', show_index=False)
    app.cleanup_ctx.append(service.turn_context)
    app.cleanup_ctx.append(service.cleanup)
    return app

if __name__ == '__main__':
    web.run_app(create_app(relay=os.environ.get('CALL_NO_RELAY')!='1'), host='127.0.0.1', port=int(os.environ.get('CALL_PORT','8092')), access_log=None)
