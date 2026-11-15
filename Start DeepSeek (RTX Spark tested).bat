@echo off
setlocal
rem Opt-in profile qualified on this RTX Spark N1X, 96 GiB GPU / 32 GiB host.
rem Requires the existing 1017 UD-IQ2_XXS weights and imatrix drafter; no new download.
cd /d "%~dp0"
call "%~dp0ds41-paths.bat"
set "DS41_CONFIG_TEMPLATE=%~dp0tools\v41\serve\profiles\rtx-spark-n1x-tested.json"
set "DS41_GGUF=%DS41_MODELS%/unsloth/UD-IQ2_XXS/DeepSeek-V4.1-Flash-1017-UD-IQ2_XXS-00001-of-00006.gguf"
set "DS41_ENGRAM=%DS41_GGUF%"
set "DS41_ARENA_GIB=8"
set "DS41_VRAM_MARGIN=24"
set "DS41_PROMPT_BATCH=512"
set "DS41_ROUTE_BIAS=0.28"
set "DS41_VISION=cpu"
if not exist "%DS41_GGUF%" (
  echo Missing the qualified UD-IQ2_XXS model. See docs\WINDOWS.md.
  exit /b 1
)
if not exist "%DS41_MODELS%/V41-1017-MTP-iq2xxs-imx.gguf" (
  echo Missing the qualified imatrix drafter. See docs\WINDOWS.md.
  exit /b 1
)
call "%~dp0Start DeepSeek.bat"
exit /b %errorlevel%
