@echo off
echo ========================================================
echo Building Assay Portable Executable
echo ========================================================

cd /d "%~dp0.."

echo.
echo [1/3] Building Next.js Frontend (Static Export)...
cd frontend
call npm run build
if %ERRORLEVEL% neq 0 (
    echo Frontend build failed!
    exit /b %ERRORLEVEL%
)
cd ..

echo.
echo [2/3] Bundling with PyInstaller...
:: Build PyInstaller spec and compile
.\venv\Scripts\pyinstaller.exe ^
  --name "Assay-Portable" ^
  --onefile ^
  --clean ^
  --add-data "frontend\out;frontend\out" ^
  --add-data "backend\alembic;backend\alembic" ^
  --add-data "alembic.ini;." ^
  --add-data "public_key.pem;." ^
  --hidden-import "passlib.handlers.bcrypt" ^
  --hidden-import "sqlmodel" ^
  backend\main.py

if %ERRORLEVEL% neq 0 (
    echo PyInstaller build failed!
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo SUCCESS: Build complete!
echo Your portable executable is located at:
echo dist\Assay-Portable.exe
echo ========================================================
pause
