@echo off
setlocal
cd /d "%~dp0"
title Salesoorja Operator - Start

echo Starting Salesoorja services...
docker compose up -d
if errorlevel 1 goto :failed

echo Waiting for Salesoorja API...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ready=$false; 1..60 | ForEach-Object { try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3; if ($r.status -eq 'healthy') { $ready=$true; return } } catch {}; Start-Sleep -Seconds 2 }; if (-not $ready) { exit 1 }"
if errorlevel 1 goto :failed

echo Starting autonomous operator...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/operator/start' -TimeoutSec 15; $r.status | ConvertTo-Json -Depth 5 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :failed

start "" "http://127.0.0.1:5173/operator"
echo.
echo Salesoorja operator start request completed.
pause
exit /b 0

:failed
echo.
echo Salesoorja could not start. Review Docker Desktop and backend logs.
pause
exit /b 1
