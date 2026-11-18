@echo off
rem Opens the StalkerTalker window (no console). For the old console view use "StalkerTalker (console).bat".
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" companion\app.py
