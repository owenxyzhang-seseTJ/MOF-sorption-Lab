#!/bin/bash

set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR" || exit 1

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$APP_DIR/launcher.py"
fi

if [ -x "/Users/xiaoyuzhang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]; then
  exec "/Users/xiaoyuzhang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" "$APP_DIR/launcher.py"
fi

osascript -e 'display dialog "没有找到可用的 Python 3。请先安装 Python 3，再重新启动 MOF Sorption Lab。" buttons {"好"} default button "好"'
