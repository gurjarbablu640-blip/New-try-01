@echo off
setlocal
cd /d "%~dp0"
title Salesoorja Operator - Stop

echo Requesting graceful Salesoorja operator stop...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/operator/stop' -TimeoutSec 15; $r.status | ConvertTo-Json -Depth 5 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :failed

echo.
echo Stop requested. The current safe unit of work will finish before final reporting.
pause
exit /b 0

:failed
echo.
echo Stop request failed. Confirm the Salesoorja backend is running.
pause
exit /b 1
