@echo off
echo ========================================================
echo Running Assay Automated Test Suite
echo ========================================================

REM Ensure we run from the project root
cd /d "%~dp0.."

REM Install test dependencies if missing
echo Checking dependencies...
call .\venv\Scripts\pip.exe install -r backend\requirements-dev.txt -q

REM Run the tests with pytest
echo Running pytest...
set PYTHONPATH=%cd%
call .\venv\Scripts\pytest.exe backend\tests -v

echo.
if %ERRORLEVEL% equ 0 (
    echo ========================================================
    echo SUCCESS: All tests passed! The platform is healthy.
    echo ========================================================
) else (
    echo ========================================================
    echo FAILURE: Some tests failed. Please check the logs above.
    echo ========================================================
)
pause
