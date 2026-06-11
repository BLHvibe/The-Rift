"""
The Rift v6 sidecar — local FastAPI process the desktop shell talks to.

Today: CORS-friendly proxy to the Fly data server (the browser/webview
can't call it cross-origin directly). Tomorrow: /engine/* (draft engine
in-process) and /lcu/* (League client integration) live here too.

Run from this directory:  uvicorn main:app --port 8765
"""
from __future__ import annotations

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

FLY_BASE = "https://the-rift-draft-sync.fly.dev"

app = FastAPI(title="rift-sidecar")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:1420",
                   "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = httpx.AsyncClient(base_url=FLY_BASE, timeout=15.0)


@app.get("/health")
async def health():
    return {"ok": True}


@app.api_route("/api/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    """Pass-through proxy for the Fly REST API."""
    url = f"/api/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    body = await request.body()
    r = await _client.request(request.method, url, content=body or None)
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type",
                                             "application/json"))
