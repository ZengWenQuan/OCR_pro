@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  start-ocr.bat - Windows equivalent of start-ocr.sh
:: ============================================================

set "PROJECT_ROOT=%~dp0"
:: Remove trailing backslash
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "FRONTEND_DIR=%PROJECT_ROOT%\ocr_frontend"
set "FRONTEND_CONFIG_FILE=%FRONTEND_DIR%\config.js"
set "FRONTEND_SERVER=%FRONTEND_DIR%\server.py"
set "ROOT_ENV_FILE=%PROJECT_ROOT%\..\..\.env"
set "UV_BIN=%UV_BIN%"
if "%UV_BIN%"=="" set "UV_BIN=%USERPROFILE%\.local\bin\uv.exe"
set "UV_CACHE_DIR=%UV_CACHE_DIR%"
if "%UV_CACHE_DIR%"=="" set "UV_CACHE_DIR=%TEMP%\uv-cache"
set "BACKEND_PORT=8100"
set "FRONTEND_PORT=8080"
set "API_HOST=%API_HOST%"

:: ---- Load .env file ----
if exist "%ROOT_ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT_ENV_FILE%") do (
        set "line=%%a"
        if not "!line:~0,1!"=="#" (
            if not "%%b"=="" (
                set "%%a=%%b"
            )
        )
    )
)

:: ---- Parse arguments ----
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--backend-port" (
    if "%~2"=="" (
        echo Missing value for --backend-port >&2
        call :usage
        exit /b 1
    )
    set "BACKEND_PORT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--frontend-port" (
    if "%~2"=="" (
        echo Missing value for --frontend-port >&2
        call :usage
        exit /b 1
    )
    set "FRONTEND_PORT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="-h" goto :show_help
if /i "%~1"=="--help" goto :show_help
echo Unexpected argument: %~1 >&2
call :usage
exit /b 1

:show_help
call :usage
exit /b 0

:args_done

:: ---- Validate ports ----
call :validate_port "%BACKEND_PORT%" "backend"
if errorlevel 1 exit /b 1

call :validate_port "%FRONTEND_PORT%" "frontend"
if errorlevel 1 exit /b 1

:: ---- Detect API_HOST ----
if "%API_HOST%"=="" (
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4" 2^>nul') do (
        set "candidate=%%a"
        set "candidate=!candidate: =!"
        if not "!candidate:~0,4!"=="127." (
            if not "!candidate!"=="::1" (
                set "API_HOST=!candidate!"
                goto :host_found
            )
        )
    )
    :host_found
    if "%API_HOST%"=="" set "API_HOST=127.0.0.1"
)

:: ---- Write frontend config ----
echo window.OCR_APP_CONFIG = { > "%FRONTEND_CONFIG_FILE%"
echo   apiBaseUrl: "http://%API_HOST%:%BACKEND_PORT%" >> "%FRONTEND_CONFIG_FILE%"
echo }; >> "%FRONTEND_CONFIG_FILE%"

:: ---- Check uv ----
if not exist "%UV_BIN%" (
    where uv >nul 2>&1
    if errorlevel 1 (
        echo uv not found at %UV_BIN% and not in PATH >&2
        exit /b 1
    )
    for /f "delims=" %%p in ('where uv') do set "UV_BIN=%%p"
)

:: ---- Ensure ports available ----
call :ensure_port_available "%BACKEND_PORT%" "Backend"
if errorlevel 1 exit /b 1

call :ensure_port_available "%FRONTEND_PORT%" "Frontend"
if errorlevel 1 exit /b 1

:: ---- Print info ----
echo Backend URL: http://%API_HOST%:%BACKEND_PORT%
echo Frontend URL: http://%API_HOST%:%FRONTEND_PORT%
echo Web page: http://%API_HOST%:%FRONTEND_PORT%/index.html

:: ---- Create cache dir ----
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"

:: ---- Start backend ----
start "OCR Backend" /b cmd /c "cd /d "%PROJECT_ROOT%" && set UV_CACHE_DIR=%UV_CACHE_DIR%&& set PYTHONPATH=%PROJECT_ROOT%&& "%UV_BIN%" run python -m flask --app ocr_backend.app run --host 0.0.0.0 --port %BACKEND_PORT%"
set "BACKEND_PID=%errorlevel%"

:: Small delay to let backend start
timeout /t 2 /nobreak >nul

:: ---- Start frontend ----
start "OCR Frontend" /b cmd /c "cd /d "%FRONTEND_DIR%" && set PYTHONPATH=%PROJECT_ROOT%&& python "%FRONTEND_SERVER%" --host 0.0.0.0 --port %FRONTEND_PORT%"
set "FRONTEND_PID=%errorlevel%"

echo.
echo OCR services started. Press Ctrl+C to stop both backend and frontend.
echo.

:: ---- Wait and cleanup ----
:: On Ctrl+C, kill child processes
:wait_loop
timeout /t 60 /nobreak >nul
goto :wait_loop

:: ============================================================
::  Subroutines
:: ============================================================

:usage
echo Usage:
echo   start-ocr.bat
echo   start-ocr.bat --backend-port 8101 --frontend-port 8081
goto :eof

:validate_port
set "p=%~1"
set "label=%~2"
:: Check it's numeric
set "numeric=1"
for /f "delims=0123456789" %%c in ("%p%") do set "numeric=0"
if "%numeric%"=="0" (
    echo Invalid %label% port: %p% >&2
    exit /b 1
)
:: Check range 1-65535
if %p% lss 1 (
    echo Invalid %label% port: %p% >&2
    exit /b 1
)
if %p% gtr 65535 (
    echo Invalid %label% port: %p% >&2
    exit /b 1
)
goto :eof

:ensure_port_available
set "port=%~1"
set "label=%~2"
set "found_pid="

for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r ":%port% .*LISTENING" 2^>nul') do (
    set "found_pid=%%a"
)

if "%found_pid%"=="" goto :eof

echo %label% port %port% is already in use by PID %found_pid%.

:: Try to check if it's our process
set "is_ours=0"
for /f "tokens=1,*" %%a in ('wmic process where "processid=%found_pid%" get commandline /format:list 2^>nul ^| findstr /i "%PROJECT_ROOT%"') do (
    set "is_ours=1"
)

if "%is_ours%"=="1" (
    echo Stopping existing OCR process on port %port% ^(PID: %found_pid%^)
    taskkill /pid %found_pid% /f >nul 2>&1 || true
    timeout /t 2 /nobreak >nul

    :: Re-check
    set "still_pid="
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r ":%port% .*LISTENING" 2^>nul') do (
        set "still_pid=%%a"
    )
    if not "!still_pid!"=="" (
        echo Port %port% is still in use: !still_pid! >&2
        echo Please free the port or start with a different one. >&2
        exit /b 1
    )
) else (
    echo Port %port% is occupied by a non-OCR process ^(PID: %found_pid%^). >&2
)

goto :eof
