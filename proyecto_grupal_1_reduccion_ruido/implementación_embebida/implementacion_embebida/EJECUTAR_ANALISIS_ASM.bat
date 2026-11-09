@echo off
setlocal
cd /d "%~dp0"
set "RESULTADOS=%~dp0Resultados_ASM"
set "SIMULACION=%~dp0nodo3_espectral_v2_validacion\datos_prueba"

if not "%~1"=="" set "RESULTADOS=%~1"
if not exist "%RESULTADOS%" (
  echo No se encontro la carpeta o ZIP de resultados:
  echo %RESULTADOS%
  echo.
  echo Coloca este .bat junto a la carpeta Resultados_ASM o arrastra el ZIP sobre el .bat.
  pause
  exit /b 1
)

if exist "%USERPROFILE%\asmvenv\Scripts\python.exe" (
  set "PYTHON_EXE=%USERPROFILE%\asmvenv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

if exist "%SIMULACION%" (
  "%PYTHON_EXE%" "%~dp0analizar_resultados_asm.py" "%RESULTADOS%" --validacion-software "%SIMULACION%"
) else (
  "%PYTHON_EXE%" "%~dp0analizar_resultados_asm.py" "%RESULTADOS%"
)

echo.
if errorlevel 1 (
  echo El analisis fallo. Revisa que Python este instalado y que las rutas sean correctas.
) else (
  echo Analisis finalizado. Consulta la carpeta Reporte_metricas.
)
pause
