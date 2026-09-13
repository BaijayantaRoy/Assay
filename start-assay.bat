@echo off
setlocal EnableExtensions EnableDelayedExpansion
::  ============================================================================
::   Assay - Developer Control Script  (Windows)
::
::   Double-click it, or run from a terminal:
::
::     start-assay.bat                 interactive menu
::     start-assay.bat fresh           stop, clean, install, start, verify
::     start-assay.bat <command> [flags]
::
::   Commands
::     fresh     stop, clear caches, reinstall, start, health-check    ^<- default
::     nuke      fresh + wipe ALL state (db, memory, vectors)     DESTRUCTIVE
::     start     start backend + frontend
::     stop      stop everything this project started
::     restart   stop + start, no cleaning
::     clean     delete caches only - never touches your data
::     reset     delete db, memory, vectors, logs                 DESTRUCTIVE
::     status    what is running, on which ports, which commit
::     doctor    full diagnostic report written to a file
::     logs      tail the most recent backend/frontend logs
::     test      run the whole test suite
::     help      this text
::
::   Flags
::     -y              skip destructive confirmations
::     --no-frontend   backend only (fastest; /docs covers the v1 work)
::     --no-install    skip dependency installation
::     --deep          with clean/nuke: also remove venv and node_modules
::     --debug         echo every command
::     --port-api N    backend port,  default 8001
::     --port-web N    frontend port, default 3001
::
::   This script never closes without saying why. Every exit path prints a
::   reason, and everything it does is appended to .assay\logs\bootstrap.log.
::  ============================================================================

:: --- Was this double-clicked from Explorer? --------------------------------
:: If so the console dies the instant we exit, so we must pause before leaving.
:: A double-clicked file is launched as:  cmd /c ""C:\...\file.bat" "
set "DOUBLECLICK=0"
echo(%cmdcmdline%| findstr /i /c:"%~nx0" >nul 2>nul && set "DOUBLECLICK=1"

cd /d "%~dp0"

set "PROJECT=Assay"
set "API_PORT=8001"
set "WEB_PORT=3001"
set "STATE_DIR=.assay\state"
set "LOG_DIR=.assay\logs"
set "BOOTLOG=.assay\logs\bootstrap.log"
set "BACKEND_TITLE=%PROJECT%-Backend"
set "FRONTEND_TITLE=%PROJECT%-Frontend"
set "ASSUME_YES=0"
set "SKIP_FRONTEND=0"
set "SKIP_INSTALL=0"
set "DEEP=0"
set "DEBUG=0"
set "EXITCODE=0"
set "FAILREASON="

if not exist ".assay"        mkdir ".assay"        >nul 2>nul
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%" >nul 2>nul
if not exist "%LOG_DIR%"   mkdir "%LOG_DIR%"   >nul 2>nul

:: Log from the very first line, so even a vanished window leaves evidence.
echo.>> "%BOOTLOG%"
echo ===== run started %DATE% %TIME% =====>> "%BOOTLOG%"
echo cwd: %CD%>> "%BOOTLOG%"
echo args: %*>> "%BOOTLOG%"

:: Timestamp. PowerShell may be slow or restricted, so it is not load-bearing.
set "TS="
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" 2^>nul') do set "TS=%%T"
if not defined TS set "TS=run%RANDOM%"

:: --- arguments -------------------------------------------------------------
set "CMD=%~1"
if "%CMD%"=="" set "CMD=menu"
shift

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="-y"            set "ASSUME_YES=1"
if /i "%~1"=="--yes"         set "ASSUME_YES=1"
if /i "%~1"=="--no-frontend" set "SKIP_FRONTEND=1"
if /i "%~1"=="--no-install"  set "SKIP_INSTALL=1"
if /i "%~1"=="--deep"        set "DEEP=1"
if /i "%~1"=="--debug"       set "DEBUG=1"
if /i "%~1"=="--port-api"    ( set "API_PORT=%~2" & shift )
if /i "%~1"=="--port-web"    ( set "WEB_PORT=%~2" & shift )
shift
goto :parse_args
:args_done

if "%DEBUG%"=="1" echo [debug] cmd=%CMD% api=%API_PORT% web=%WEB_PORT% doubleclick=%DOUBLECLICK%
call :log "command %CMD%"

if /i "%CMD%"=="menu"    goto :cmd_menu
if /i "%CMD%"=="fresh"   goto :cmd_fresh
if /i "%CMD%"=="nuke"    goto :cmd_nuke
if /i "%CMD%"=="start"   goto :cmd_start
if /i "%CMD%"=="stop"    goto :cmd_stop
if /i "%CMD%"=="restart" goto :cmd_restart
if /i "%CMD%"=="clean"   goto :cmd_clean
if /i "%CMD%"=="reset"   goto :cmd_reset
if /i "%CMD%"=="status"  goto :cmd_status
if /i "%CMD%"=="doctor"  goto :cmd_doctor
if /i "%CMD%"=="logs"    goto :cmd_logs
if /i "%CMD%"=="test"    goto :cmd_test
if /i "%CMD%"=="help"    goto :cmd_help
if /i "%CMD%"=="-h"      goto :cmd_help
if /i "%CMD%"=="--help"  goto :cmd_help

set "FAILREASON=Unknown command '%CMD%'. Run this file with 'help' to see the list."
set "EXITCODE=2"
goto :finish


:: ===========================================================================
:cmd_menu
call :banner
echo    1.  fresh    stop, clear caches, reinstall, start, verify
echo    2.  start    just start it
echo    3.  stop     stop everything
echo    4.  restart  stop then start
echo    5.  status   what is running right now
echo    6.  doctor   write a full diagnostic report
echo    7.  logs     show recent server output
echo    8.  clean    delete caches, keeps your data
echo    9.  test     run the test suite
echo   10.  reset    DELETE db, memory, vectors
echo   11.  nuke     reset + fresh, from scratch
echo    0.  exit
echo.
set "PICK="
set /p "PICK=   Choose [1]: "
if "%PICK%"=="" set "PICK=1"
if "%PICK%"=="1"  goto :cmd_fresh
if "%PICK%"=="2"  goto :cmd_start
if "%PICK%"=="3"  goto :cmd_stop
if "%PICK%"=="4"  goto :cmd_restart
if "%PICK%"=="5"  goto :cmd_status
if "%PICK%"=="6"  goto :cmd_doctor
if "%PICK%"=="7"  goto :cmd_logs
if "%PICK%"=="8"  goto :cmd_clean
if "%PICK%"=="9"  goto :cmd_test
if "%PICK%"=="10" goto :cmd_reset
if "%PICK%"=="11" goto :cmd_nuke
if "%PICK%"=="0"  goto :finish
echo    Not a valid choice.
goto :cmd_menu


:: ===========================================================================
:cmd_fresh
call :banner
echo   FRESH START - caches cleared, your data kept
echo.
call :stop_all
call :clean_caches
call :preflight
if not "!EXITCODE!"=="0" goto :finish
call :ensure_venv
if not "!EXITCODE!"=="0" goto :finish
if "%SKIP_INSTALL%"=="0" (
    call :install_deps
    if not "!EXITCODE!"=="0" goto :finish
)
call :start_backend
if "%SKIP_FRONTEND%"=="0" call :start_frontend
call :wait_ready
call :collect_status
call :summary
goto :finish

:cmd_nuke
call :banner
echo   NUKE - this DELETES your prompt database, agent memory and vectors.
echo.
call :confirm "Wipe all state and rebuild from scratch"
if not "!EXITCODE!"=="0" goto :finish
call :stop_all
call :reset_state
call :clean_caches
call :preflight
if not "!EXITCODE!"=="0" goto :finish
call :ensure_venv
if not "!EXITCODE!"=="0" goto :finish
call :install_deps
if not "!EXITCODE!"=="0" goto :finish
call :start_backend
if "%SKIP_FRONTEND%"=="0" call :start_frontend
call :wait_ready
call :collect_status
call :summary
goto :finish

:cmd_start
call :banner
call :preflight
if not "!EXITCODE!"=="0" goto :finish
call :ensure_venv
if not "!EXITCODE!"=="0" goto :finish
if "%SKIP_INSTALL%"=="0" (
    call :install_deps
    if not "!EXITCODE!"=="0" goto :finish
)
call :start_backend
if "%SKIP_FRONTEND%"=="0" call :start_frontend
call :wait_ready
call :summary
goto :finish

:cmd_stop
call :banner
call :stop_all
echo.
echo   Stopped.
goto :finish

:cmd_restart
call :banner
call :stop_all
call :preflight
if not "!EXITCODE!"=="0" goto :finish
call :ensure_venv
if not "!EXITCODE!"=="0" goto :finish
call :start_backend
if "%SKIP_FRONTEND%"=="0" call :start_frontend
call :wait_ready
call :summary
goto :finish

:cmd_clean
call :banner
call :clean_caches
echo.
echo   Caches cleared. Your data was not touched.
goto :finish

:cmd_reset
call :banner
echo   RESET - this DELETES the prompt database, agent memory and vectors.
echo.
call :confirm "Delete all local state"
if not "!EXITCODE!"=="0" goto :finish
call :stop_all
call :reset_state
echo.
echo   State cleared. Run this script again to rebuild.
goto :finish

:cmd_status
call :banner
call :collect_status
type "%STATUS_FILE%"
echo.
echo   Saved to %STATUS_FILE%
goto :finish

:cmd_logs
call :banner
call :show_log "%LOG_DIR%\backend-latest.log"  "BACKEND"
call :show_log "%LOG_DIR%\frontend-latest.log" "FRONTEND"
echo.
echo   Startup trace: %CD%\%BOOTLOG%
goto :finish

:cmd_test
call :banner
call :preflight
if not "!EXITCODE!"=="0" goto :finish
call :ensure_venv
if not "!EXITCODE!"=="0" goto :finish
echo   Core tests...
venv\Scripts\python.exe -m pytest packages\assay-core\tests -q
set "RC1=!errorlevel!"
echo.
echo   Backend tests...
venv\Scripts\python.exe -m pytest backend\tests -q
set "RC2=!errorlevel!"
echo.
if "!RC1!"=="0" if "!RC2!"=="0" (
    echo   All tests passed.
    goto :finish
)
set "FAILREASON=Tests failed. core=!RC1!  backend=!RC2!"
set "EXITCODE=4"
goto :finish

:cmd_help
call :banner
echo   COMMANDS
echo     fresh     stop, clear caches, reinstall, start, health-check
echo     nuke      fresh + wipe ALL state                     DESTRUCTIVE
echo     start     start backend + frontend
echo     stop      stop everything this project started
echo     restart   stop + start, no cleaning
echo     clean     delete caches only - never touches your data
echo     reset     delete db, memory, vectors, logs           DESTRUCTIVE
echo     status    what is running, ports, commit
echo     doctor    full diagnostic report to a file
echo     logs      tail recent server output
echo     test      run the whole test suite
echo.
echo   FLAGS
echo     -y   --no-frontend   --no-install   --deep   --debug
echo     --port-api N    --port-web N
echo.
echo   EXAMPLES
echo     start-assay.bat                      menu
echo     start-assay.bat fresh                everyday restart
echo     start-assay.bat fresh --no-frontend  API only, quickest
echo     start-assay.bat doctor               report for a bug
goto :finish


:: ===========================================================================
:cmd_doctor
call :banner
set "DOC=%STATE_DIR%\doctor-%TS%.txt"
echo   Collecting diagnostics. The test suite runs, so allow a minute.
echo.
> "%DOC%" echo ============================================================
>>"%DOC%" echo  %PROJECT% diagnostic report
>>"%DOC%" echo  generated %DATE% %TIME%
>>"%DOC%" echo  root      %CD%
>>"%DOC%" echo ============================================================

call :doc_head "TOOLCHAIN"
call :preflight >nul 2>nul
set "EXITCODE=0"
>>"%DOC%" echo python cmd: !PYTHON_CMD!
for /f "delims=" %%V in ('!PYTHON_CMD! --version 2^>^&1') do >>"%DOC%" echo python:  %%V
for /f "delims=" %%V in ('node --version 2^>^&1')          do >>"%DOC%" echo node:    %%V
for /f "delims=" %%V in ('git --version 2^>^&1')           do >>"%DOC%" echo git:     %%V

call :doc_head "GIT"
for /f "delims=" %%V in ('git rev-parse --abbrev-ref HEAD 2^>^&1') do >>"%DOC%" echo branch: %%V
for /f "delims=" %%V in ('git rev-parse --short HEAD 2^>^&1')      do >>"%DOC%" echo commit: %%V
git status --short >> "%DOC%" 2>&1

call :doc_head "PORTS"
call :port_report %API_PORT% backend
call :port_report %WEB_PORT% frontend

call :doc_head "HEALTH"
call :probe "http://127.0.0.1:%API_PORT%/health"    "backend /health"
call :probe "http://127.0.0.1:%API_PORT%/v1/health" "api /v1/health"
call :probe "http://127.0.0.1:%API_PORT%/docs"      "swagger /docs"
call :probe "http://127.0.0.1:%WEB_PORT%"           "frontend"

call :doc_head "ENVIRONMENT - names only, never values"
call :key_present OPENAI_API_KEY
call :key_present ANTHROPIC_API_KEY
call :key_present GOOGLE_API_KEY
call :key_present ASSAY_WORKSPACE
if exist ".env" ( >>"%DOC%" echo   .env: present ) else ( >>"%DOC%" echo   .env: absent )

call :doc_head "DISK"
call :size_report "venv"                  "python venv"
call :size_report "frontend\node_modules" "node modules"
call :size_report "chroma_data"           "vector store"
call :size_report ".assay\memory"           "agent memory"
if exist "database.db" ( >>"%DOC%" echo   database.db: present ) else ( >>"%DOC%" echo   database.db: absent )

call :doc_head "PLUGINS"
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "from assay_core import get_registry; d=get_registry().describe(); [print(f'  {g:20s} {len(v):3d}') for g,v in sorted(d.items()) if v]; print(f'  TOTAL {sum(len(v) for v in d.values())}'); bad=[(g,r['name'],r['error']) for g,v in d.items() for r in v if r['error']]; print('  load failures: ' + (str(bad) if bad else 'none'))" >> "%DOC%" 2>&1
) else ( >>"%DOC%" echo   venv not built )

call :doc_head "TESTS"
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -m pytest packages\assay-core\tests -q >> "%DOC%" 2>&1
    venv\Scripts\python.exe -m pytest backend\tests -q >> "%DOC%" 2>&1
) else ( >>"%DOC%" echo   venv not built )

call :doc_head "BOOTSTRAP TRACE - last 40 lines"
powershell -NoProfile -Command "Get-Content '%BOOTLOG%' -Tail 40" >> "%DOC%" 2>&1

call :doc_head "BACKEND LOG - last 40 lines"
if exist "%LOG_DIR%\backend-latest.log" (
    powershell -NoProfile -Command "Get-Content '%LOG_DIR%\backend-latest.log' -Tail 40" >> "%DOC%" 2>&1
) else ( >>"%DOC%" echo   no backend log )

echo   Report written to:
echo     %CD%\%DOC%
echo.
echo   It records whether a key is set, never its value. Safe to share.
goto :finish


:: ===========================================================================
::  SUBROUTINES
:: ===========================================================================

:log
echo [%TIME%] %~1>> "%BOOTLOG%" 2>nul
goto :eof

:banner
echo.
echo  ==============================================================
echo   %PROJECT%  -  dev control
echo  ==============================================================
echo.
goto :eof

:confirm
if "%ASSUME_YES%"=="1" goto :eof
set "ANS="
set /p "ANS=  %~1? Type YES to continue: "
if /i "!ANS!"=="YES" goto :eof
set "FAILREASON=Cancelled. Nothing was changed."
set "EXITCODE=1"
goto :eof


:preflight
call :log "preflight"
set "PYTHON_CMD="
where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "C:\Python313\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
    ) do if not defined PYTHON_CMD if exist %%P set "PYTHON_CMD=%%~P"
)
if not defined PYTHON_CMD (
    set "FAILREASON=Python was not found. Install 3.10 or newer from https://www.python.org/downloads/ and tick 'Add python.exe to PATH' during setup."
    set "EXITCODE=1"
    goto :eof
)
echo   [ok] python  !PYTHON_CMD!
call :log "python !PYTHON_CMD!"
if "%SKIP_FRONTEND%"=="0" (
    where node >nul 2>nul
    if !errorlevel! neq 0 (
        set "FAILREASON=Node.js was not found. Install it from https://nodejs.org/ , or re-run with --no-frontend to start only the API."
        set "EXITCODE=1"
        goto :eof
    )
    echo   [ok] node
)
goto :eof


:ensure_venv
if not exist "venv\Scripts\python.exe" (
    echo   [..] creating virtual environment - first run takes a moment
    call :log "creating venv"
    "!PYTHON_CMD!" -m venv venv >> "%BOOTLOG%" 2>&1
)
if not exist "venv\Scripts\python.exe" (
    set "FAILREASON=Could not create the virtual environment. The error is at the end of %BOOTLOG%."
    set "EXITCODE=1"
    goto :eof
)
echo   [ok] venv
goto :eof


:install_deps
echo   [..] installing python dependencies
call :log "pip install requirements"
venv\Scripts\python.exe -m pip install --upgrade pip --quiet >> "%BOOTLOG%" 2>&1
venv\Scripts\python.exe -m pip install -r backend\requirements.txt --quiet >> "%BOOTLOG%" 2>&1
if !errorlevel! neq 0 (
    set "FAILREASON=Backend dependency install failed. The reason is at the end of %BOOTLOG%."
    set "EXITCODE=1"
    goto :eof
)
:: The project was called MyPromptLibrary and shipped an `mpl` CLI until ADR-0009. A venv
:: created before that still has mpl-core/mpl-cli/mpl-mcp installed, .pth files pointing at
:: packages\mpl-core\src (a directory that no longer exists) and an mpl.exe on PATH.
:: pip will not remove them, because the new distributions have different names — so the
:: two sets sit side by side and the stale half breaks imports and entry-point discovery.
venv\Scripts\python.exe -m pip show mpl-core >nul 2>nul
if !errorlevel! equ 0 (
    echo   [..] removing packages left over from before the rename to Assay
    call :log "uninstall stale mpl-* distributions"
    venv\Scripts\python.exe -m pip uninstall -y mpl-core mpl-cli mpl-mcp mypromptlibrary >> "%BOOTLOG%" 2>&1
    del /q "venv\Lib\site-packages\_editable_impl_mpl_*.pth" >nul 2>nul
    del /q "venv\Lib\site-packages\__editable__.mpl_*"       >nul 2>nul
    del /q "venv\Scripts\mpl.exe" "venv\Scripts\mpl-mcp.exe" >nul 2>nul
    echo   [ok] stale packages removed
)

call :log "pip install assay packages"
venv\Scripts\python.exe -m pip install -e packages\assay-core -e packages\assay-cli -e packages\assay-mcp --quiet >> "%BOOTLOG%" 2>&1
if !errorlevel! neq 0 (
    set "FAILREASON=Install of the assay packages failed. See the end of %BOOTLOG%."
    set "EXITCODE=1"
    goto :eof
)

:: pip exiting 0 does not mean the package imports. An editable install whose target
:: directory was renamed leaves pip perfectly happy and Python unable to find anything,
:: which is precisely the state a rename produces. Check the thing we actually need.
venv\Scripts\python.exe -c "import assay_core, assay_cli" >> "%BOOTLOG%" 2>&1
if !errorlevel! neq 0 (
    set "FAILREASON=The assay packages installed but cannot be imported - usually a venv left over from an older checkout. Delete the 'venv' folder and run this file again; it will rebuild in a few minutes."
    set "EXITCODE=1"
    goto :eof
)
echo   [ok] python dependencies
if "%SKIP_FRONTEND%"=="0" (
    if not exist "frontend\node_modules" (
        echo   [..] installing frontend dependencies - this takes a few minutes
        call :log "npm install"
        pushd frontend
        call npm install >> "..\%BOOTLOG%" 2>&1
        set "NPMRC=!errorlevel!"
        popd
        if !NPMRC! neq 0 (
            set "FAILREASON=npm install failed. See %BOOTLOG%, or re-run with --no-frontend to skip the web UI."
            set "EXITCODE=1"
            goto :eof
        )
    )
    echo   [ok] frontend dependencies
)
goto :eof


:stop_all
echo   [..] stopping anything already running
call :kill_port %API_PORT% backend
call :kill_port %WEB_PORT% frontend
taskkill /FI "WINDOWTITLE eq %BACKEND_TITLE%*"  /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq %FRONTEND_TITLE%*" /T /F >nul 2>nul
echo   [ok] stopped
goto :eof


:kill_port
set "PORT=%~1"
set "LABEL=%~2"
set "FOUND=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:"LISTENING" ^| findstr /C:":%PORT% "') do (
    if not "%%P"=="0" (
        taskkill /PID %%P /T /F >nul 2>nul
        if !errorlevel! equ 0 (
            echo        stopped %LABEL% pid %%P
            set "FOUND=1"
        )
    )
)
if "!FOUND!"=="0" echo        port %PORT% was already free
goto :eof


:clean_caches
echo   [..] clearing caches
call :rmdir_quiet ".pytest_cache"  "pytest cache"
call :rmdir_quiet "frontend\out"   "next export"
call :rmdir_quiet ".ruff_cache"    "ruff cache"
:: frontend\.next is deliberately NOT deleted here. It is Next.js's incremental
:: build cache - typically ~90 MB - and removing it forces a full cold compile that
:: takes minutes. Clearing it on every start made the frontend look broken while it
:: was merely rebuilding. It is only removed by --deep and by nuke.
if "%DEEP%"=="1" call :rmdir_quiet "frontend\.next" "next build cache"
:: Scan only the source trees. A repo-wide scan walks venv and node_modules,
:: which takes far longer than the deletes it is looking for.
for %%R in (backend packages scripts prompts spec docs) do (
    if exist "%%R" (
        for /f "delims=" %%D in ('dir /s /b /ad "%%R\__pycache__" 2^>nul') do rd /s /q "%%D" 2>nul
        for /f "delims=" %%D in ('dir /s /b /ad "%%R\*.egg-info" 2^>nul') do rd /s /q "%%D" 2>nul
    )
)
if exist "__pycache__" rd /s /q "__pycache__" 2>nul
echo        removed __pycache__ and egg-info
if "%DEEP%"=="1" (
    call :rmdir_quiet "venv"                  "python venv"
    call :rmdir_quiet "frontend\node_modules" "node modules"
)
echo   [ok] caches cleared
goto :eof


:reset_state
echo   [..] deleting local state
if exist "database.db" (
    copy /y "database.db" "%STATE_DIR%\database-backup-%TS%.db" >nul 2>nul
    del /f /q "database.db" >nul 2>nul
    echo        database.db deleted - a backup is in %STATE_DIR%
)
call :rmdir_quiet "chroma_data" "vector store"
call :rmdir_quiet ".assay\memory" "agent memory"
if exist "%APPDATA%\%PROJECT%" (
    rd /s /q "%APPDATA%\%PROJECT%" 2>nul
    echo        removed %APPDATA%\%PROJECT%
)
echo   [ok] state cleared
goto :eof


:rmdir_quiet
if exist "%~1" (
    rd /s /q "%~1" 2>nul
    echo        removed %~2
)
goto :eof


:start_backend
echo   [..] starting backend on port %API_PORT%
if not defined ASSAY_WORKSPACE set "ASSAY_WORKSPACE=%CD%"
set "BE_LOG=%LOG_DIR%\backend-latest.log"
:: A generated launcher avoids nested quotes inside `start`, which is the most
:: reliable way to break a batch file, and it survives paths containing spaces.
:: The launcher pauses on exit so a crashed server leaves its error on screen.
> ".assay\run-backend.cmd" echo @echo off
>>".assay\run-backend.cmd" echo title %BACKEND_TITLE%
>>".assay\run-backend.cmd" echo cd /d "%CD%"
>>".assay\run-backend.cmd" echo set "ASSAY_WORKSPACE=%ASSAY_WORKSPACE%"
>>".assay\run-backend.cmd" echo set "PYTHONUNBUFFERED=1"
>>".assay\run-backend.cmd" echo venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port %API_PORT% ^> "%BE_LOG%" 2^>^&1
>>".assay\run-backend.cmd" echo echo.
>>".assay\run-backend.cmd" echo echo Backend stopped. The log is %BE_LOG%
>>".assay\run-backend.cmd" echo pause
call :log "launching backend"
start "%BACKEND_TITLE%" /min cmd /c ".assay\run-backend.cmd"
goto :eof


:start_frontend
echo   [..] starting frontend on port %WEB_PORT%
set "FE_LOG=%LOG_DIR%\frontend-latest.log"
> ".assay\run-frontend.cmd" echo @echo off
>>".assay\run-frontend.cmd" echo title %FRONTEND_TITLE%
>>".assay\run-frontend.cmd" echo cd /d "%CD%\frontend"
>>".assay\run-frontend.cmd" echo call npm run dev ^> "%CD%\%FE_LOG%" 2^>^&1
>>".assay\run-frontend.cmd" echo echo.
>>".assay\run-frontend.cmd" echo echo Frontend stopped. The log is %FE_LOG%
>>".assay\run-frontend.cmd" echo pause
call :log "launching frontend"
start "%FRONTEND_TITLE%" /min cmd /c ".assay\run-frontend.cmd"
goto :eof


:wait_ready
:: The backend answers in a couple of seconds. Next.js compiles on first request and
:: can take minutes when its cache is cold, so the two get very different budgets -
:: giving them the same one is what made the frontend look broken.
echo   [..] waiting for services to answer
if "%SKIP_FRONTEND%"=="0" echo        the frontend compiles on first start; a cold build can take 1-3 minutes
set "API_UP=0"
set "WEB_UP=0"
if "%SKIP_FRONTEND%"=="1" set "WEB_UP=1"
for /l %%I in (1,1,180) do (
    if "!API_UP!"=="0" (
        call :http_code "http://127.0.0.1:%API_PORT%/health"
        if "!CODE!"=="200" (
            set "API_UP=1"
            echo        backend  ready after %%I s
        )
    )
    if "!WEB_UP!"=="0" (
        call :http_code "http://127.0.0.1:%WEB_PORT%"
        :: Next.js binds the port before it can serve, so "answered" is not
        :: "ready". Only a 2xx/3xx counts; a 5xx means it started and is failing.
        if "!CODE!"=="200" set "WEB_UP=1"
        if "!CODE!"=="307" set "WEB_UP=1"
        if "!CODE!"=="308" set "WEB_UP=1"
        if "!WEB_UP!"=="1" echo        frontend ready after %%I s
        if "!CODE!"=="500" (
            set "WEB_UP=2"
            echo        frontend is running but returning errors - see its window
        )
    )
    if "!API_UP!"=="1" if "!WEB_UP!"=="1" goto :wait_done
    :: Backend up but frontend still compiling: say so, rather than sitting silent.
    if "!API_UP!"=="1" if "!WEB_UP!"=="0" (
        set /a "MOD=%%I %% 15"
        if "!MOD!"=="0" echo        still compiling the frontend... %%I s
    )
    timeout /t 1 /nobreak >nul
)
:wait_done
if "!API_UP!"=="0" (
    set "EXITCODE=1"
    set "FAILREASON=The backend did not answer on port %API_PORT% within 40 seconds. Its own window, titled '%BACKEND_TITLE%', stays open with the error. The last lines of its log are printed above."
    echo   [X] backend did not become healthy
    echo.
    echo   ---- last 20 lines of the backend log ----------------------
    if exist "%LOG_DIR%\backend-latest.log" (
        powershell -NoProfile -Command "Get-Content '%LOG_DIR%\backend-latest.log' -Tail 20" 2>nul
    ) else (
        echo   No log was written, so the process may not have started at all.
        echo   Run this by hand to see the real error:
        echo     venv\Scripts\python.exe -m uvicorn backend.main:app --port %API_PORT%
    )
    echo   -----------------------------------------------------------
) else (
    echo   [ok] backend healthy
)
if "%SKIP_FRONTEND%"=="0" if "!WEB_UP!"=="0" (
    echo.
    echo   [!] The frontend has not answered after 3 minutes.
    echo       It may still be compiling - the window titled "%FRONTEND_TITLE%"
    echo       is still running. Try http://localhost:%WEB_PORT% in a minute.
    echo.
    echo   ---- last 20 lines of the frontend log ---------------------
    if exist "%LOG_DIR%\frontend-latest.log" (
        powershell -NoProfile -Command "Get-Content '%LOG_DIR%\frontend-latest.log' -Tail 20" 2>nul
        echo   -----------------------------------------------------------
        echo   Note: Next.js buffers its output when redirected, so this log
        echo   often lags. The server window itself is the live view.
    ) else (
        echo   No frontend log yet.
        echo   Run this by hand to see the real error:
        echo     cd frontend  ^&^&  npm run dev
        echo   -----------------------------------------------------------
    )
)
goto :eof


:http_code
set "CODE=0"
for /f %%C in ('powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri '%~1' -UseBasicParsing -TimeoutSec 3).StatusCode}catch{0}" 2^>nul') do set "CODE=%%C"
goto :eof


:show_log
if exist "%~1" (
    echo.
    echo   ---- %~2  last 40 lines ------------------------------------
    powershell -NoProfile -Command "Get-Content '%~1' -Tail 40" 2>nul
) else (
    echo   %~2: no log yet
)
goto :eof


:collect_status
set "STATUS_FILE=%STATE_DIR%\status-%TS%.txt"
set "STATUS_JSON=%STATE_DIR%\status-%TS%.json"
call :http_code "http://127.0.0.1:%API_PORT%/health"
set "API_CODE=!CODE!"
call :http_code "http://127.0.0.1:%WEB_PORT%"
set "WEB_CODE=!CODE!"
set "API_STATE=down"
if not "!API_CODE!"=="0" set "API_STATE=up"
set "WEB_STATE=down"
if not "!WEB_CODE!"=="0" set "WEB_STATE=up"
set "GIT_BRANCH=unknown"
set "GIT_COMMIT=unknown"
for /f "delims=" %%V in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "GIT_BRANCH=%%V"
for /f "delims=" %%V in ('git rev-parse --short HEAD 2^>nul')      do set "GIT_COMMIT=%%V"

> "%STATUS_FILE%" echo   %PROJECT% status - %DATE% %TIME%
>>"%STATUS_FILE%" echo.
>>"%STATUS_FILE%" echo   backend   http://127.0.0.1:%API_PORT%     !API_STATE!   HTTP !API_CODE!
>>"%STATUS_FILE%" echo   frontend  http://127.0.0.1:%WEB_PORT%     !WEB_STATE!   HTTP !WEB_CODE!
>>"%STATUS_FILE%" echo   api docs  http://127.0.0.1:%API_PORT%/docs
>>"%STATUS_FILE%" echo.
>>"%STATUS_FILE%" echo   git       !GIT_BRANCH! @ !GIT_COMMIT!
if exist "venv\Scripts\python.exe" (
    for /f "delims=" %%V in ('venv\Scripts\python.exe --version 2^>^&1') do >>"%STATUS_FILE%" echo   python    %%V
) else ( >>"%STATUS_FILE%" echo   python    venv not built )
if exist "database.db" ( >>"%STATUS_FILE%" echo   database  present ) else ( >>"%STATUS_FILE%" echo   database  absent )
if exist ".assay\memory" ( >>"%STATUS_FILE%" echo   memory    present ) else ( >>"%STATUS_FILE%" echo   memory    empty )

> "%STATUS_JSON%" echo {
>>"%STATUS_JSON%" echo   "timestamp": "%TS%",
>>"%STATUS_JSON%" echo   "backend":  { "port": %API_PORT%, "state": "!API_STATE!", "http": "!API_CODE!" },
>>"%STATUS_JSON%" echo   "frontend": { "port": %WEB_PORT%, "state": "!WEB_STATE!", "http": "!WEB_CODE!" },
>>"%STATUS_JSON%" echo   "git": { "branch": "!GIT_BRANCH!", "commit": "!GIT_COMMIT!" }
>>"%STATUS_JSON%" echo }
goto :eof


:doc_head
>>"%DOC%" echo.
>>"%DOC%" echo ------------------------------------------------------------
>>"%DOC%" echo  %~1
>>"%DOC%" echo ------------------------------------------------------------
goto :eof

:probe
call :http_code "%~1"
if "!CODE!"=="0" ( >>"%DOC%" echo   %~2: DOWN ) else ( >>"%DOC%" echo   %~2: HTTP !CODE! )
goto :eof

:port_report
set "ANY=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:"LISTENING" ^| findstr /C:":%~1 "') do (
    set "ANY=1"
    >>"%DOC%" echo   port %~1 %~2: pid %%P
)
if "!ANY!"=="0" >>"%DOC%" echo   port %~1 %~2: free
goto :eof

:key_present
if defined %~1 ( >>"%DOC%" echo   %~1: set ) else ( >>"%DOC%" echo   %~1: not set )
goto :eof

:size_report
if exist "%~1" (
    for /f %%S in ('powershell -NoProfile -Command "try{'{0:N1} MB' -f ((Get-ChildItem -LiteralPath '%~1' -Recurse -Force -ErrorAction SilentlyContinue ^| Measure-Object -Property Length -Sum).Sum/1MB)}catch{'?'}" 2^>nul') do >>"%DOC%" echo   %~2: %%S
) else ( >>"%DOC%" echo   %~2: absent )
goto :eof


:summary
echo.
echo  ==============================================================
if "!EXITCODE!"=="0" ( echo   RUNNING ) else ( echo   PROBLEM - see the message below )
echo  ==============================================================
if "!EXITCODE!"=="0" (
    echo.
    echo    Web UI     http://localhost:%WEB_PORT%
    echo               browse and edit PromptFiles - stable /v1 workbench
    echo    API docs   http://localhost:%API_PORT%/docs
    echo               harness, loop, memory, redteam, calibration
    echo    Health     http://localhost:%API_PORT%/health
    echo.
    if "%SKIP_FRONTEND%"=="0" (
        if "!WEB_UP!"=="1" (
            echo    Opening both in your browser.
            start "" "http://localhost:%WEB_PORT%"
        ) else (
            echo    Opening the API docs. The web UI is still compiling -
            echo    open http://localhost:%WEB_PORT% once it finishes.
        )
    )
    start "" "http://localhost:%API_PORT%/docs"
    echo.
    echo    Two minimised server windows are open, titled
    echo    "%BACKEND_TITLE%" and "%FRONTEND_TITLE%".
    echo    Close them to stop, or run this file with 'stop'.
)
goto :eof


:: ===========================================================================
::  SINGLE EXIT POINT - never leave without saying why
:: ===========================================================================
:finish
if defined FAILREASON (
    echo.
    echo  --------------------------------------------------------------
    echo   STOPPED
    echo  --------------------------------------------------------------
    echo.
    echo   !FAILREASON!
    echo.
    :: Show the tail inline. Telling someone a log file exists and making them go open it
    :: is how "it just didn't work" reports happen — the answer is usually in these lines.
    echo   --- last 15 lines of %BOOTLOG% ---
    powershell -NoProfile -Command "Get-Content -Tail 15 '%BOOTLOG%' 2>$null | ForEach-Object { '   ' + $_ }" 2>nul
    echo   ----------------------------------
    echo.
    echo   Full trace:  %CD%\%BOOTLOG%
    echo   Full report: start-assay.bat doctor
    call :log "FAILED !FAILREASON!"
) else (
    call :log "finished ok"
)
echo.
if "%DOUBLECLICK%"=="1" (
    echo   Press any key to close this window...
    pause >nul
)
endlocal & exit /b %EXITCODE%
