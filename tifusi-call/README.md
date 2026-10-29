# هم‌صدا — Tifusi Call

Persian, mobile-first, two-person audio/video calls. One person creates a room and shares its guest link. No accounts or recording. A room expires after one hour; either participant ending the call closes it for both. A link's fragment contains a bearer invitation: share it only with the intended guest.

## Architecture

- `dist/`: buildless static browser application, also published as a public Site for anonymous invitation access.
- `server.py`: independent aiohttp signaling/API service, bound to loopback port 8092. `/call/` also serves a self-hosted copy of the frontend. Production CORS/WebSocket origins are explicitly listed.
- WebRTC carries encrypted audio/video directly when possible, with authenticated coturn fallback on public UDP/TCP 3478. UDP relay allocation range: 49160–49259. Media is not recorded by this application. No claim of extra end-to-end identity verification is made.
- The supervisor starts coturn with a random secret in an anonymous memory fd; it never persists that secret in a file or command-line argument. Browser TURN credentials are scoped to room/role and expire shortly after room expiry. On service restart, all in-memory rooms and the relay secret are replaced; participants must create a new room.
- One host and one guest WebSocket slot per room. A duplicate participant is rejected. One deterministic offerer and pre-negotiated audio/video transceivers support camera toggles without simultaneous offers. Signaling generations discard old ICE messages after reconnection.
- Limited room creation/message rates, room cap, origin validation, expired/revoked token checks, no access logging of invite tokens, and private/metadata peer-address restrictions on the relay.

## Operations

Requires Python 3.12, aiohttp 3.x and coturn (`turnserver`). `deploy/tifusi-call.service` runs under the existing unprivileged `turnserver` account. Install source at `/opt/tifusi-call`, validate the unit, start it, and merge only `deploy/Caddy.snippet` into the existing HTTPS host before its fallback route. Validate Caddy before reload. Existing applications do not need a restart. The distribution coturn unit stays masked because this service owns its authenticated child process.

Health: `/call/health`. Runtime configuration names: `CALL_PORT` (8092), `CALL_TURN_IP` (public IPv4), `CALL_TURN_PORT` (3478). `CALL_NO_RELAY=1` is for isolated signaling tests only. No `.env` or API token is needed. For production TLS, Caddy provides HTTPS; TURN currently supports UDP/TCP 3478, not TURN TLS over 443. Networks blocking those TURN transports can still fail.

To roll back a fresh installation, stop/disable only `tifusi-call`, remove its newly added Caddy route by restoring/merging the saved pre-change configuration, validate and reload Caddy. Do not restore other application files or stop Caddy. Source, logs and backups can remain. No DNS or panel changes are part of this deployment.

## Verification

`python3 -m unittest discover -s tests -p 'test_*.py' -v` checks room authorization, duplicate prevention, signaling generation, expiry, hangup, origin rejection and creation limits with isolated in-process servers.

`tests/check_browser.py` uses Playwright Chromium with synthetic microphone/camera devices and **real** RTCPeerConnection/WebSocket/TURN media; no media/signaling mocks. It checks bidirectional audio bytes/video frames using forced relay, third-party rejection, mic/camera controls, reconnection, full track cleanup, audio-only mode, and responsive layouts. The local test server runs on 127.0.0.1:8093 with that test origin explicitly added and a real TURN instance. Set `CALL_TEST_URL` and `CALL_TEST_OUTPUT` to change the browser test target/output.

Synthetic devices and same-host browser contexts do not replace physical Safari/iOS/Android or two actual consumer-network tests. Camera/microphone permission prompts, browser autoplay, mobile camera switching and background suspension still require real-device checks. Permission errors are shown explicitly; playback has a tap-to-play fallback. No background-call guarantee is made. A page leaving releases its devices; a brief disconnected peer can rejoin while the room remains valid.

The static font is Noto Sans Arabic under OFL; see `dist/OFL.txt`.
