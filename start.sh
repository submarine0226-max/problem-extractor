#!/usr/bin/env sh
# 문제 추출기 (macOS / Linux): ./start.sh
# 설치(처음 한 번) -> API 키 입력 -> 서버 켜기 -> 브라우저 열기
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  PY=""
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 &&
       "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$cand"
      break
    fi
  done
  if [ -z "$PY" ]; then
    echo "Python 3.10 이상이 필요해요."
    echo "  macOS: brew install python  (또는 https://www.python.org/downloads/)"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    exit 1
  fi
  echo "처음 실행이라 준비하고 있어요..."
  "$PY" -m venv .venv || {
    echo "가상환경을 만들지 못했어요. Ubuntu/Debian이면: sudo apt install python3-venv"
    exit 1
  }
fi

exec .venv/bin/python scripts/launch.py "$@"
