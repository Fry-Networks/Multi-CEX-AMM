@echo off
REM Multi-CEX-AMM Bot Launcher for Windows
REM
REM Usage:
REM   run_bot.bat              - Run the bot
REM   run_bot.bat --setup      - Set up virtual environment and install dependencies
REM   run_bot.bat --help       - Show help message

setlocal enabledelayedexpansion

REM Script directory
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"

REM Colors (limited in CMD)
set "COLOR_RESET="

echo.
echo ================================================================
echo            MULTI-EXCHANGE AMM BOT
echo.
echo    Exchanges: NonKYC ^| Bitstorage ^| Exbitron
echo ================================================================
echo.

REM Parse arguments
if "%1"=="--help" goto :help
if "%1"=="-h" goto :help
if "%1"=="--setup" goto :setup
if "%1"=="--config" goto :config

goto :run

:help
echo Multi-CEX-AMM Bot Launcher
echo.
echo Usage:
echo   run_bot.bat              Run the bot
echo   run_bot.bat --setup      Set up virtual environment and install dependencies
echo   run_bot.bat --config     Create config.json from template
echo   run_bot.bat --help       Show this help message
echo.
echo Configuration:
echo   1. Copy config.example.json to config.json
echo   2. Edit config.json with your API credentials
echo   3. Set "enabled": true for the exchanges you want to use
echo   4. Run the bot with run_bot.bat
echo.
goto :end

:check_python
REM Try to find Python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python"
    goto :check_version
)

where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python3"
    goto :check_version
)

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=py -3"
    goto :check_version
)

echo ERROR: Python 3 is not installed.
echo Please install Python 3.8 or higher from https://www.python.org/
echo Make sure to check "Add Python to PATH" during installation.
exit /b 1

:check_version
REM Check Python version
for /f "tokens=*" %%i in ('%PYTHON_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYTHON_VERSION=%%i
for /f "tokens=*" %%i in ('%PYTHON_CMD% -c "import sys; print(sys.version_info.major)"') do set PYTHON_MAJOR=%%i
for /f "tokens=*" %%i in ('%PYTHON_CMD% -c "import sys; print(sys.version_info.minor)"') do set PYTHON_MINOR=%%i

if %PYTHON_MAJOR% lss 3 (
    echo ERROR: Python 3.8 or higher is required.
    echo Current version: %PYTHON_VERSION%
    exit /b 1
)

if %PYTHON_MAJOR% equ 3 if %PYTHON_MINOR% lss 8 (
    echo ERROR: Python 3.8 or higher is required.
    echo Current version: %PYTHON_VERSION%
    exit /b 1
)

echo Found Python %PYTHON_VERSION%
exit /b 0

:setup
call :check_python
if %ERRORLEVEL% neq 0 exit /b 1

echo Setting up virtual environment...

if exist "%VENV_DIR%" (
    echo Virtual environment already exists at %VENV_DIR%
    set /p "CONFIRM=Do you want to recreate it? (y/N): "
    if /i "!CONFIRM!"=="y" (
        echo Removing existing virtual environment...
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo Keeping existing virtual environment.
        goto :install_deps
    )
)

echo Creating virtual environment...
%PYTHON_CMD% -m venv "%VENV_DIR%"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
)

echo Created virtual environment at %VENV_DIR%

:install_deps
REM Activate virtual environment
call "%VENV_DIR%\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing dependencies...
if exist "%SCRIPT_DIR%requirements.txt" (
    pip install -r "%SCRIPT_DIR%requirements.txt"
) else (
    pip install aiohttp
)

if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to install dependencies.
    exit /b 1
)

echo.
echo Setup complete!
echo.
echo Next steps:
echo   1. Copy config.example.json to config.json
echo   2. Edit config.json with your API credentials
echo   3. Run: run_bot.bat
echo.
goto :end

:config
if exist "%SCRIPT_DIR%config.json" (
    echo config.json already exists.
    set /p "CONFIRM=Do you want to overwrite it? (y/N): "
    if /i not "!CONFIRM!"=="y" (
        echo Keeping existing config.json
        goto :end
    )
)

if exist "%SCRIPT_DIR%config.example.json" (
    copy "%SCRIPT_DIR%config.example.json" "%SCRIPT_DIR%config.json" >nul
    echo Created config.json from template.
    echo Please edit config.json with your API credentials.
) else (
    echo ERROR: config.example.json not found.
    exit /b 1
)
goto :end

:run
call :check_python
if %ERRORLEVEL% neq 0 exit /b 1

REM Activate virtual environment if it exists
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
    echo Activated virtual environment
)

REM Check if aiohttp is installed
%PYTHON_CMD% -c "import aiohttp" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: aiohttp is not installed.
    echo Run: run_bot.bat --setup
    exit /b 1
)

REM Check for config.json
if not exist "%SCRIPT_DIR%config.json" (
    echo Warning: config.json not found.
    echo Using default configuration from amm_bot.py
    echo Run "run_bot.bat --config" to create a config file.
    echo.
)

REM Run the bot
cd /d "%SCRIPT_DIR%"
%PYTHON_CMD% amm_bot.py %*

:end
endlocal
