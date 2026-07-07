#!/bin/bash
# NPZ Tactical Map — Dashboard HTTP Server
# Usage: ./serve.sh [port]
PORT=${1:-8081}
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "🛢️  НПЗ Панель Агентов — http://localhost:$PORT/"
echo "   Остановка: Ctrl+C"
cd "$DIR"
python3 -m http.server "$PORT"
