@echo off
echo ============================================
echo   PDF Tools - Installing dependencies...
echo ============================================
echo.
pip install flask PyMuPDF Pillow python-docx pywin32 rembg onnxruntime
echo.
echo ============================================
echo   Installation complete!
echo   Run start.bat to launch the app.
echo ============================================
pause
