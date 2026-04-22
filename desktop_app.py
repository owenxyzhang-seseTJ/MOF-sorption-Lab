from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

from waitress import serve

from app import app

BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR / "static" / "mof-sorption-lab-icon-256.png"
HOST = "127.0.0.1"
PORT = 5055
APP_URL = f"http://{HOST}:{PORT}"


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(host, port):
            return True
        time.sleep(0.2)
    return False


def run_server() -> None:
    serve(app, host=HOST, port=PORT, threads=8)


def main() -> int:
    if not port_open(HOST, PORT):
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        if not wait_for_port(HOST, PORT):
            raise RuntimeError("MOF Sorption Lab server did not start in time.")
    try:
        import webview

        window = webview.create_window(
            "MOF Sorption Lab",
            APP_URL,
            width=1440,
            height=940,
            min_size=(1180, 760),
        )
        webview.start(icon=str(ICON_PATH) if ICON_PATH.exists() else None, debug=False)
        return 0
    except Exception:
        webbrowser.open(APP_URL)
        while True:
            time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
