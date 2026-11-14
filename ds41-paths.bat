@echo off
rem ---- The settings for this PC (the launcher and setup-ds41-models.bat read them) ----------------------------
rem DS41_MODELS: the folder that holds (or will hold) the model files - on your fastest NVMe drive, ~371 GB.
rem   Default: the "models" folder in this repository.  Change it here, or set an environment variable of the
rem   same name (that wins).  Example: set "DS41_MODELS=D:/DeepSeek-V4.1"
if not defined DS41_MODELS set "DS41_MODELS=c:/Users/michael/models/deepseek-ai/DeepSeek-V4.1-Flash-1017"
rem DS41_PORT: the port the server listens on: apps use http://127.0.0.1:<port>/v1.  Default 8080 - change it here if
rem   another program on this PC uses 8080.
if not defined DS41_PORT set "DS41_PORT=8080"
rem DS41_GPU: the NVIDIA GPU to run on, counted in PCI bus order (nvidia-smi's order; 0 = the first card).
rem   Default: the card with the most VRAM (the first of equals) - set it here to choose another.
if defined DS41_GPU goto gpu_done
set "DS41_GPU=0"
set "DS41_GPU_MIB=0"
for /f "tokens=1,2 delims=, " %%a in ('nvidia-smi --query-gpu^=index^,memory.total --format^=csv^,noheader^,nounits 2^>nul') do call :pick_gpu %%a %%b
set "DS41_GPU_MIB="
goto gpu_done
:pick_gpu
rem nvidia-smi can also list an NPU with memory.total=[N/A]. Only compare numbers.
echo %2| findstr /r "^[0-9][0-9]*$" >nul || exit /b 0
if %2 GTR %DS41_GPU_MIB% (
  set "DS41_GPU=%1"
  set "DS41_GPU_MIB=%2"
)
exit /b 0
:gpu_done
rem Optional: DS41_ARENA_GIB=N fixes the RAM arena (default: sized from your installed RAM, see
rem   tools\v41\serve\ds41_local.py); DS41_RAM_RESERVE_GIB=N leaves N GiB for Windows and other programs (default 28);
rem   DS41_VRAM_MARGIN=N keeps N GiB of VRAM free beside the expert cache (default 0.6) - raise it if other programs
rem   use the card.
rem   DS41_PROMPT_BATCH=N limits tokens processed together (default: the model config). Smaller batches need less
rem   GPU workspace; model-specific safety caps still apply. Restart Start DeepSeek.bat after changing settings.
rem Local memory settings for this RTX Spark (excluded from PR patches).
rem Current split: 96 GiB dedicated GPU memory, about 30.5 GiB visible to Windows.
rem The old 64 GiB arena was for the 24 GiB GPU split and cannot fit this host allocation.
rem Measured 2026-11-13: upload working-set trim recovers RAM for an 8 GiB expert arena.
rem The 512 MiB staging halves avoid a pinned-buffer failure seen with 1024 MiB and margin 8.
rem Four coding checks improved 10-23 percent; a 23742-token prompt retained 4.2 GiB host RAM.
rem Results: logs/spark-normal-profile-validation/results.json. Images were not benchmarked.
rem Explicit environment settings still win. Re-benchmark after changing the memory split.
if not defined STRATA_DS41_TRIM_UPLOAD_WS set "STRATA_DS41_TRIM_UPLOAD_WS=1"
if not defined MIMO_CHUNK_STAGE_MIB set "MIMO_CHUNK_STAGE_MIB=512"
if not defined DS41_ARENA_GIB set "DS41_ARENA_GIB=8"
if not defined DS41_VRAM_MARGIN set "DS41_VRAM_MARGIN=8"
rem The earlier 24 GiB GPU split passed six requests through 21K tokens on 2026-11-09.
rem The engine may reduce this limit to fit GPU memory. Recheck these local settings if changing models.
if not defined DS41_PROMPT_BATCH set "DS41_PROMPT_BATCH=12288"
