@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

start "Financial Command Center" cmd /k "cd /d ""%~dp0"" && streamlit run ui/app.py --server.port 8501"
start "Data Input Studio" cmd /k "cd /d ""%~dp0"" && streamlit run ui/repository.py --server.port 8502"

timeout /t 5 /nobreak >nul

start "" "http://localhost:8501"
start "" "http://localhost:8502"

endlocal
