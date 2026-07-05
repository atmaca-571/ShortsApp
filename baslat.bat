@echo off
title Katmanli Animasyon Motoru - Kurulum ve Baslatma
color 0D

echo ============================================
echo   PYTHON KABA KURGU MOTORU
echo   (Katmanli Animasyon Sistemi)
echo   Kurulum ve Baslatma
echo ============================================
echo.

echo [1/2] Gerekli kutuphaneler kontrol ediliyor / kuruluyor...
echo (Ilk seferde birkac dakika surebilir, internetin acik olsun)
echo.
pip install --quiet moviepy Pillow

if errorlevel 1 (
    echo.
    echo HATA: Kutuphaneler kurulamadi. Python ve pip kurulu mu kontrol et.
    pause
    exit /b
)

echo [2/2] Kutuphaneler hazir. Motor calistiriliyor...
echo.
echo ============================================
python app.py
echo ============================================
echo.
echo Islem bitti. Video varsa 'output_shorts' klasorunde.
pause
