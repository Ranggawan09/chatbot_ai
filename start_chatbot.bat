@echo off
title Jalankan Chatbot Adatku (Rasa + Actions + Cloudflare)
echo =============================================
echo   MEMULAI CHATBOT ADATKU
echo =============================================
echo.

:: === Atur lokasi project Rasa (ubah sesuai folder kamu)
cd /d "C:\Users\ranggawan\Documents\chatbot_ai"

:: === Jalankan Action Server di jendela baru
start cmd /k "title Rasa Actions Server & rasa run actions --port 5055"

:: Tunggu 5 detik agar Action Server sempat jalan
timeout /t 5 /nobreak >nul

:: === Jalankan Rasa utama (API Server)
start cmd /k "title Rasa Core Server & rasa run --enable-api --cors \"*\" --port 5005"

:: Tunggu 5 detik lagi
timeout /t 5 /nobreak >nul

:: === Jalankan Cloudflare Tunnel
start cmd /k "title Cloudflare Tunnel & cloudflared tunnel run rasa-chatbot"

echo.
echo Semua service sudah dijalankan!
pause
