@echo off
echo ========================================
echo  IMAP Plugin - Update Libraries
echo ========================================
echo.

:: Check if uv is installed
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: uv is not installed or not in PATH
    echo Please install uv first: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

echo [1/4] Updating all dependencies to latest versions...
uv lock --upgrade
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to update lock file
    pause
    exit /b 1
)

echo.
echo [2/4] Syncing updated dependencies...
uv sync --all-extras
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to sync dependencies
    pause
    exit /b 1
)

echo.
echo [3/4] Running linting checks...
uv run ruff check src/ tests/
if %ERRORLEVEL% neq 0 (
    echo WARNING: Linting issues found
)

uv run mypy src/
if %ERRORLEVEL% neq 0 (
    echo WARNING: Type checking issues found
)

echo.
echo [4/4] Running tests...
uv run pytest tests/ -q
if %ERRORLEVEL% neq 0 (
    echo WARNING: Some tests failed after update
    echo You may need to fix compatibility issues
)

echo.
echo ========================================
echo  Update complete!
echo ========================================
echo.
pause
