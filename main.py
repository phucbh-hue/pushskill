import asyncio
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response

app = FastAPI(title="Last30Days MCP Gateway")

BUNDLE_PATH = Path(__file__).with_name("last30days-pp-mcp-linux-amd64.mcpb")
EXTRACT_ROOT = Path(os.environ.get("MCP_BUNDLE_DIR", "/tmp/last30days-mcp"))
BINARY_PATH = EXTRACT_ROOT / "bin" / "last30days-pp-mcp"
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "").strip()
MCP_PROTOCOL_VERSION = "2025-06-18"
sessions: dict[str, "McpSession"] = {}
sessions_lock = asyncio.Lock()


def ensure_binary() -> Path:
    if BINARY_PATH.exists():
        return BINARY_PATH
    if not BUNDLE_PATH.exists():
        raise RuntimeError(f"MCP bundle not found: {BUNDLE_PATH}")
    EXTRACT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=EXTRACT_ROOT.parent) as temp_dir:
        temp_root = Path(temp_dir) / "bundle"
        with zipfile.ZipFile(BUNDLE_PATH) as bundle:
            bundle.extractall(temp_root)
        extracted_binary = temp_root / "bin" / "last30days-pp-mcp"
        if not extracted_binary.exists():
            raise RuntimeError("MCP bundle does not contain bin/last30days-pp-mcp")
        if EXTRACT_ROOT.exists():
            shutil.rmtree(EXTRACT_ROOT)
        shutil.copytree(temp_root, EXTRACT_ROOT)
    BINARY_PATH.chmod(0o755)
    return BINARY_PATH


def check_auth(authorization: str | None) -> None:
    if MCP_AUTH_TOKEN and authorization != f"Bearer {MCP_AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid MCP authorization")


class McpSession:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        self.process = await asyncio.create_subprocess_exec(
            str(ensure_binary()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=os.environ.copy(),
        )

    async def request(self, message: dict) -> dict | None:
        if self.process is None:
            await self.start()
        assert self.process is not None
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        async with self.lock:
            self.process.stdin.write((json.dumps(message) + "\n").encode())
            await self.process.stdin.drain()
            if "id" not in message:
                return None
            while True:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=300)
                if not line:
                    raise RuntimeError("Last30Days MCP process exited without a response")
                payload = json.loads(line.decode())
                if "id" in payload:
                    return payload

    async def close(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mcp_bundle": BUNDLE_PATH.exists(),
        "mcp_auth": bool(MCP_AUTH_TOKEN),
    }


@app.post("/mcp")
async def mcp(request: Request, authorization: str | None = Header(default=None)) -> Response:
    check_auth(authorization)
    try:
        message = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="MCP body must be JSON") from exc
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise HTTPException(status_code=400, detail="MCP body must be a JSON-RPC 2.0 object")

    session_id = request.headers.get("Mcp-Session-Id")
    if message.get("method") == "initialize":
        session_id = str(uuid.uuid4())
        session = McpSession()
        async with sessions_lock:
            sessions[session_id] = session
    elif not session_id or session_id not in sessions:
        raise HTTPException(status_code=400, detail="Missing or unknown Mcp-Session-Id")
    else:
        session = sessions[session_id]

    try:
        result = await session.request(message)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="MCP tool timed out after 300 seconds") from exc
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        async with sessions_lock:
            sessions.pop(session_id, None)
        await session.close()
        raise HTTPException(status_code=502, detail=f"MCP process failed: {exc}") from exc

    headers = {"Mcp-Session-Id": session_id, "MCP-Protocol-Version": MCP_PROTOCOL_VERSION}
    if result is None:
        return Response(status_code=202, headers=headers)
    return Response(content=json.dumps(result), media_type="application/json", headers=headers)


@app.delete("/mcp")
async def close_mcp(request: Request, authorization: str | None = Header(default=None)) -> Response:
    check_auth(authorization)
    session_id = request.headers.get("Mcp-Session-Id")
    if session_id:
        async with sessions_lock:
            session = sessions.pop(session_id, None)
        if session:
            await session.close()
    return Response(status_code=204)
