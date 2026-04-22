from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
APP_FILE = APP_DIR / "app.py"
REQUIREMENTS_FILE = APP_DIR / "requirements.txt"
VENV_DIR = APP_DIR / ".venv"
VENDOR_DIR = APP_DIR / ".vendor"
LOG_FILE = APP_DIR / ".mof-sorption-lab.log"
STAMP_FILE = VENV_DIR / ".requirements.sha256"
HOST = "127.0.0.1"
PORT = 5055
APP_URL = f"http://{HOST}:{PORT}"


def server_running() -> bool:
    try:
        with urllib.request.urlopen(APP_URL, timeout=1.2) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def open_browser() -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", APP_URL], cwd=APP_DIR)
            return
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", "start", "", APP_URL], cwd=APP_DIR, shell=False)
            return
        subprocess.Popen(["xdg-open", APP_URL], cwd=APP_DIR)
        return
    except Exception:
        webbrowser.open(APP_URL)


def requirements_hash() -> str:
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()


def current_venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python3"


def vendor_runtime_works() -> bool:
    if not VENDOR_DIR.exists():
        return False
    probe = (
        "import sys; "
        f"sys.path.insert(0, {str(VENDOR_DIR)!r}); "
        "import flask, pandas, scipy, openpyxl, pygaps, pyiast, CoolProp; "
        "print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0 and "ok" in result.stdout


def ensure_venv() -> Path:
    python_bin = current_venv_python()
    if not python_bin.exists():
        venv.create(VENV_DIR, with_pip=True, clear=False, symlinks=os.name != "nt")
    desired_hash = requirements_hash()
    installed_hash = STAMP_FILE.read_text(encoding="utf-8").strip() if STAMP_FILE.exists() else ""
    if installed_hash != desired_hash:
        subprocess.check_call([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], cwd=APP_DIR)
        subprocess.check_call([str(python_bin), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)], cwd=APP_DIR)
        STAMP_FILE.write_text(desired_hash, encoding="utf-8")
    return python_bin


def launch_server() -> None:
    env = os.environ.copy()
    env["MOF_SORPTION_HOST"] = HOST
    env["MOF_SORPTION_PORT"] = str(PORT)
    env["MOF_SORPTION_DEBUG"] = "0"
    env.pop("PYTHONPATH", None)
    env.pop("MOF_SORPTION_USE_VENDOR", None)
    python_cmd = [sys.executable]
    if vendor_runtime_works():
        env["MOF_SORPTION_USE_VENDOR"] = "1"
        env["PYTHONPATH"] = str(VENDOR_DIR)
    else:
        python_cmd = [str(ensure_venv())]
    stdout_handle = open(LOG_FILE, "a", encoding="utf-8")
    stderr_handle = subprocess.STDOUT
    kwargs = {
        "cwd": APP_DIR,
        "env": env,
        "stdout": stdout_handle,
        "stderr": stderr_handle,
        "close_fds": os.name != "nt",
    }
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(python_cmd + [str(APP_FILE)], **kwargs)


def wait_for_server(timeout_seconds: float = 25.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if server_running():
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    if server_running():
        open_browser()
        return 0
    try:
        launch_server()
    except subprocess.CalledProcessError as exc:
        print("依赖安装或启动失败：", exc)
        print(f"请查看日志：{LOG_FILE}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print("启动失败：", exc)
        print(f"请查看日志：{LOG_FILE}")
        return 1
    if wait_for_server():
        open_browser()
        return 0
    print("MOF Sorption Lab 启动超时。")
    print(f"请查看日志：{LOG_FILE}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
