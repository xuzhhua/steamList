@echo off
rem SteamList deploy wrapper: bypasses PowerShell execution policy for deploy.ps1.
rem Usage: deploy.cmd -RemoteUser <user> [-RemoteHost <host>] [-DryRun] ...
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1" %*
exit /b %ERRORLEVEL%
