@echo off
cd /d "%~dp0\.."

echo [1/4] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 goto error

echo [2/4] Collecting telemetry (this takes a while)...
python telemetry/scanner.py --probes 3
if errorlevel 1 goto error

echo [3/4] Training model...
python ml/trainer.py
if errorlevel 1 goto error

echo [4/4] Evaluating...
python analysis/evaluate.py
if errorlevel 1 goto error

echo.
echo Done. Results are in the results\ folder.
pause
exit /b 0

:error
echo.
echo Something went wrong. Check the error above.
pause
exit /b 1
