@echo off
cd /d "%~dp0"
call myenv\Scripts\activate
pythonw orb.py
