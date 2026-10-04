@echo off
start "Excel 입력 도우미" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0excel-workbook-bridge.ps1"
