"""처음 쓰는 사람용 실행기. start.bat / start.sh 가 이 파일을 부른다.

하는 일
  1. 필요한 패키지가 없거나 pyproject.toml이 바뀌었으면 설치
  2. .env가 없으면 만들고, Gemini API 키를 물어서 저장
  3. 서버를 켜고 브라우저를 연다 (이미 켜져 있으면 브라우저만 연다)

표준 라이브러리만 쓴다. 패키지 설치 전에 돌아야 하니까.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
KEY_URL = "https://aistudio.google.com/apikey"


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------- 설치


def ensure_installed() -> None:
    if sys.prefix == sys.base_prefix:
        say("※ 가상환경(.venv) 밖에서 실행 중이에요. start.bat / start.sh 로 실행하는 걸 권장해요.")
    marker = Path(sys.prefix) / ".problem-extractor-installed"
    want = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    if marker.is_file() and marker.read_text().strip() == want:
        return
    say("필요한 패키지를 설치하고 있어요. 처음 한 번만 1~3분쯤 걸려요...")
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-e", str(ROOT)]
    if subprocess.call(cmd) != 0:
        say("\n설치에 실패했어요. 위 오류 메시지를 확인해 주세요. (인터넷 연결이 필요해요)")
        sys.exit(1)
    marker.write_text(want)
    say("설치 완료!\n")


# --------------------------------------------------------------------- .env / 키


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV.is_file():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def set_env_value(key: str, value: str) -> None:
    text = ENV.read_text(encoding="utf-8") if ENV.is_file() else ""
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    text = pattern.sub(line, text, count=1) if pattern.search(text) else text.rstrip("\n") + f"\n{line}\n"
    ENV.write_text(text, encoding="utf-8")


def ensure_env(ask_key: bool) -> None:
    if not ENV.is_file():
        ENV.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        say("설정 파일(.env)을 만들었어요.")
    env = read_env()
    provider = (os.environ.get("PX_PROVIDER") or env.get("PX_PROVIDER") or "gemini").lower()
    if provider != "gemini":
        return
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or env.get("GEMINI_API_KEY"):
        return
    if not ask_key or not sys.stdin.isatty():
        say("※ Gemini API 키가 아직 없어요. 화면은 열리지만 사진 추출은 키를 넣어야 돼요.")
        return

    say("=" * 60)
    say(" 사진에서 문제를 뽑으려면 Google Gemini API 키가 필요해요 (무료).")
    say(f" 1) 브라우저에서 {KEY_URL} 를 열고 구글 계정으로 로그인")
    say(" 2) 'Create API key' 를 눌러 키를 복사")
    say(" 3) 아래에 붙여넣고 Enter (나중에 하려면 그냥 Enter)")
    say("=" * 60)
    try:
        webbrowser.open(KEY_URL)
    except Exception:
        pass
    try:
        key = input("API 키: ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        key = ""
    if not key:
        say("키 없이 시작해요. 나중에 .env 파일의 GEMINI_API_KEY= 뒤에 넣으면 돼요.\n")
        return
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", key):
        say("※ 키 모양이 조금 이상해요. 그래도 저장할게요. 안 되면 .env에서 고쳐 주세요.")
    set_env_value("GEMINI_API_KEY", key)
    say("키를 .env에 저장했어요. (이 파일은 git에 올라가지 않아요)\n")


# --------------------------------------------------------------------- 서버


def health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as res:
            return json.loads(res.read())
    except Exception:
        return None


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def open_when_ready(port: int) -> None:
    for _ in range(60):
        if health(port):
            webbrowser.open(f"http://localhost:{port}")
            return
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="문제 추출기 실행")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않기")
    parser.add_argument("--no-key-prompt", action="store_true", help="API 키를 묻지 않기")
    args = parser.parse_args()

    os.chdir(ROOT)  # 서버가 .env와 data/를 여기서 찾는다
    # 방금 설치한 패키지는 이 프로세스의 import 경로에 아직 없으니, 프로젝트 폴더를 직접 넣는다.
    sys.path.insert(0, str(ROOT))
    ensure_installed()
    ensure_env(ask_key=not args.no_key_prompt)

    port = args.port
    if health(port):
        say(f"이미 서버가 켜져 있어요: http://localhost:{port}")
        if not args.no_browser:
            webbrowser.open(f"http://localhost:{port}")
        return
    while not port_free(port):
        port += 1

    import uvicorn  # 설치 뒤에 불러온다

    say(f"서버를 켰어요 → http://localhost:{port}")
    say("이 창을 닫으면 서버가 꺼져요. (끄기: Ctrl+C)\n")
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()
    uvicorn.run("problem_extractor.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
