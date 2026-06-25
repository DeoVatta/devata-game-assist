"""
OBS WebSocket detection — checks if OBS is running with Forza as a source.
Used for stream automation triggers.

Method:
1. Check OBS process running (obs64.exe / obs32.exe)
2. Connect to OBS WebSocket (obs-websocket plugin) if enabled
3. Query scene sources for Forza window/capture

Requires: obs-websocket plugin installed in OBS.
Default port: 4455, default password: empty (configurable).
"""
import socket
import hashlib
import base64
import struct
import json
import uuid
import asyncio
from typing import Optional


def is_obs_running() -> bool:
    """Check if OBS process is running."""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"].lower()
                if "obs" in name or "obs64" in name:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except Exception:
        # Fallback: check if port 4455 is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 4455))
        sock.close()
        return result == 0


async def _obs_websocket_call(host, port, password, op_code, data=None):
    """Low-level OBS WebSocket send/receive via asyncio + websockets stdlib fallback."""
    try:
        import websockets
        uri = f"ws://{host}:{port}"
        async with websockets.connect(uri, extra_headers={"Origin": "http://localhost"}) as ws:
            # Auth if needed
            if password:
                auth_resp = await ws.recv()
                auth_data = json.loads(auth_resp)
                if auth_data.get("d", {}).get("authentication"):
                    auth = auth_data["d"]["authentication"]
                    secret = base64.b64encode(
                        hashlib.sha256((password + auth["salt"]).encode()).digest()
                    )
                    auth_resp["d"]["authentication"]["secret"] = base64.b64encode(
                        hashlib.sha256(
                            secret + auth["salt"].encode() + auth["challenge"].encode()
                        ).digest()
                    ).decode()
                    await ws.send(json.dumps(auth_resp))
            msg = {"op": op_code, "d": data or {}}
            await ws.send(json.dumps(msg))
            resp = await ws.recv()
            return json.loads(resp)
    except ImportError:
        # websockets not installed — use raw socket WebSocket handshake
        return await _obs_raw_ws(host, port, password, op_code, data)


async def _obs_raw_ws(host, port, password, op_code, data):
    """Fallback: raw WebSocket handshake using http.client + socket."""
    import http.client

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((host, port))

    key = base64.b64encode(uuid.uuid4().bytes).decode().strip()
    handshake = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.send(handshake.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += sock.recv(4096)

    def ws_send(sock, payload):
        payload_bytes = json.dumps(payload).encode()
        frame = bytearray()
        frame.append(0x81)  # FIN + text frame
        length = len(payload_bytes)
        if length < 126:
            frame.append(0x80 | length)  # masked
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack(">H", length))
        mask = uuid.uuid4().bytes
        frame.extend(mask)
        frame.extend(bytes(a ^ b for a, b in zip(payload_bytes, mask * (len(payload_bytes) // 4 + 1))))
        sock.send(bytes(frame))

    def ws_recv(sock):
        data = sock.recv(4096)
        if not data or data[0] & 0x0F == 0x08:
            return None
        payload_len = data[1] & 0x7F
        mask = data[2:6]
        payload = data[6:6 + payload_len]
        return bytes(a ^ b for a, b in zip(payload, mask * (payload_len // 4 + 1))).decode()

    msg = {"op": op_code, "d": data or {}}
    ws_send(sock, msg)
    result = ws_recv(sock)
    sock.close()
    return json.loads(result) if result else None


def _sync_obs_call(host, port, password, op_code, data=None):
    """Synchronous wrapper around async OBS WebSocket call."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_obs_websocket_call(host, port, password, op_code, data))


def get_obs_sources(host: str = "localhost", port: int = 4455, password: str = None) -> list:
    """
    Connect to OBS WebSocket and return all scene sources.
    Returns list of source names.
    """
    try:
        result = _sync_obs_call(host, port, password, 6, {"requestType": "GetSceneList", "requestId": str(uuid.uuid4())})
        scenes = result.get("d", {}).get("responseData", {}).get("scenes", [])
        all_sources = []
        for scene in scenes:
            scene_name = scene.get("sceneName", "")
            items_resp = _sync_obs_call(host, port, password, 6, {
                "requestType": "GetSceneItemList",
                "requestId": str(uuid.uuid4()),
                "requestData": {"sceneName": scene_name}
            })
            for src in items_resp.get("d", {}).get("responseData", {}).get("sceneItems", []):
                src_name = src.get("sourceName", "")
                if src_name:
                    all_sources.append({
                        "scene": scene_name,
                        "source": src_name,
                        "type": "",
                    })
        return all_sources
    except Exception:
        return []


def is_forza_in_obs_sources(host: str = "localhost", port: int = 4455, password: str = None) -> bool:
    """Return True if any Forza-related source is in OBS scenes."""
    sources = get_obs_sources(host, port, password)
    for_name_keywords = ["forza", "fh", "horizon"]
    for src in sources:
        name = src.get("source", "").lower()
        for kw in for_name_keywords:
            if kw in name:
                return True
    return False


def detect(host: str = "localhost", port: int = 4455, password: str = None) -> bool:
    """Source-level detect() — True if Forza is an active OBS source."""
    if not is_obs_running():
        return False
    return is_forza_in_obs_sources(host, port, password)
