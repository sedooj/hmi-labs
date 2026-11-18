#!/bin/sh
# Запуск приложения на macOS/Linux. При первом запуске создаёт .venv и ставит зависимости.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || exit 1
fi
exec .venv/bin/python main.py "$@"
