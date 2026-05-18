# 一键创建 conda 环境并安装依赖
# 用法（在 Anaconda PowerShell 或刷新 PATH 后的 PowerShell 里跑）：
#   .\scripts\setup_env.ps1

$ErrorActionPreference = "Stop"
$ENV_NAME = "notegen"
$PY_VER = "3.10"
$CUDA = "cu121"   # 与 PyTorch 索引对齐

Write-Host "==> 检查 conda..." -ForegroundColor Cyan
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Host "找不到 conda。请先关闭并重新打开 PowerShell，或运行：" -ForegroundColor Red
    Write-Host "  & `"$env:USERPROFILE\miniconda3\Scripts\conda.exe`" init powershell"
    exit 1
}

Write-Host "==> 创建环境 $ENV_NAME (python=$PY_VER)..." -ForegroundColor Cyan
$envs = conda env list 2>$null | Out-String
if ($envs -match "^\s*$ENV_NAME\s") {
    Write-Host "环境 $ENV_NAME 已存在，跳过创建"
} else {
    conda create -n $ENV_NAME python=$PY_VER -y
}

Write-Host "==> 在 $ENV_NAME 中安装 PyTorch ($CUDA)..." -ForegroundColor Cyan
conda run -n $ENV_NAME --no-capture-output pip install torch torchvision torchaudio --index-url "https://download.pytorch.org/whl/$CUDA"

Write-Host "==> 安装其余依赖..." -ForegroundColor Cyan
conda run -n $ENV_NAME --no-capture-output pip install -r requirements.txt

Write-Host "==> 验证..." -ForegroundColor Cyan
conda run -n $ENV_NAME --no-capture-output python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
conda run -n $ENV_NAME --no-capture-output python -c "from faster_whisper import WhisperModel; print('faster-whisper OK')"

Write-Host ""
Write-Host "✅ 环境就绪。激活方式：" -ForegroundColor Green
Write-Host "    conda activate $ENV_NAME" -ForegroundColor Green
