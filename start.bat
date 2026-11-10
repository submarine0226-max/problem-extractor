@echo off
rem 문제 추출기: 더블클릭하면 설치(처음 한 번) -> API 키 입력 -> 서버 켜기 -> 브라우저 열기
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Problem Extractor

if exist ".venv\Scripts\python.exe" goto run

rem ---- Python 3.10 이상 찾기 (py 런처 -> python 순서)
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if defined PY goto makevenv
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if defined PY goto makevenv
goto nopython

:makevenv
echo 처음 실행이라 준비하고 있어요...
%PY% -m venv .venv
if errorlevel 1 goto venvfail

:run
".venv\Scripts\python.exe" scripts\launch.py %*
if errorlevel 1 pause
exit /b

:nopython
echo.
echo Python 3.10 이상이 필요해요. 아래 중 하나로 설치한 뒤 이 파일을 다시 실행해 주세요.
echo.
echo   1) https://www.python.org/downloads/ 에서 받아 설치
echo      (설치 첫 화면에서 "Add python.exe to PATH" 를 꼭 체크)
echo   2) 또는 PowerShell 에서:  winget install Python.Python.3.13
echo.
pause
exit /b 1

:venvfail
echo 가상환경(.venv)을 만들지 못했어요. 위 오류 메시지를 확인해 주세요.
pause
exit /b 1
