@echo off
rem 더블클릭하면 서버가 켜져요. 이 창을 닫으면 서버도 꺼져요.
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo .venv 가 없어요. README의 빠른 시작대로 설치해 주세요.
  pause
  exit /b 1
)
echo 서버를 켜는 중... 브라우저에서 http://localhost:8000 을 여세요.
echo 끄려면 이 창을 닫거나 Ctrl+C 를 누르세요.
".venv\Scripts\python.exe" -m uvicorn problem_extractor.main:app --port 8000
pause
