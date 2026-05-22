@echo off
setlocal

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_lan.py %*
) else (
    python run_lan.py %*
)
