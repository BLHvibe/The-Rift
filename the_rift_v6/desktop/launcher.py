"""
The Rift v6 desktop launcher.

One process: serves the built web app + proxies /api to the Fly server,
then opens a native WebView2 window onto it. Falls back to Edge app-mode,
then the default browser, if pywebview can't start.

Build (from the_rift_v6/desktop, after `npm run build` and copying
app/dist -> desktop/web):
  pyinstaller --noconfirm --onefile --noconsole --name TheRiftV6
    --add-data "web;web" --collect-all webview --collect-all clr_loader
    --collect-all pythonnet launcher.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time

# Windowed (--noconsole) builds have no stdout/stderr — anything that
# writes (uvicorn logging!) would raise and kill the server thread.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

FLY = "https://the-rift-draft-sync.fly.dev"
APP_NAME = "The Rift"
BG = "#060d1a"


def res_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


app = FastAPI()
_client = httpx.Client(base_url=FLY, timeout=15.0)


@app.api_route("/api/{path:path}", methods=["GET", "POST"])
def proxy(path: str, request: Request):
    url = f"/api/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    r = _client.request(request.method, url)
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type",
                                             "application/json"))


app.mount("/", StaticFiles(directory=res_path("web"), html=True))


def serve(port: int):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def wait_ready(port: int, timeout=15.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            httpx.get(f"http://127.0.0.1:{port}/", timeout=2.0)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    port = free_port()
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    ok = wait_ready(port)
    url = f"http://127.0.0.1:{port}/"

    if "--headless" in sys.argv:           # build smoke test
        r = httpx.get(url + "api/stats", timeout=10.0)
        try:
            print(f"selftest: ready={ok} stats={r.status_code}")
        except Exception:
            pass                            # --noconsole has no stdout
        sys.exit(0 if ok and r.status_code == 200 else 1)

    try:
        import webview
        webview.create_window(APP_NAME, url, width=1480, height=920,
                              background_color=BG)
        webview.start()
        return
    except Exception:
        pass
    # Fallback 1: Edge app-mode (chromeless window, uses system Edge).
    try:
        import subprocess
        p = subprocess.Popen(["cmd", "/c", "start", "/wait", "msedge",
                              f"--app={url}"])
        p.wait()
        return
    except Exception:
        pass
    # Fallback 2: default browser; keep serving until closed.
    import webbrowser
    webbrowser.open(url)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
