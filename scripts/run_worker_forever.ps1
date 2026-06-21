# worker 守护：崩溃自动重启（ROADMAP 阶段 B #5 的本机替代 NSSM 方案）。
# 正常退出（exit 0，如 Ctrl+C 优雅停）不重启；异常退出按指数退避重启（5s→60s 封顶）。
# 重启记录追加到 logs\worker_restarts.log。
# Run:  powershell -ExecutionPolicy Bypass -File scripts\run_worker_forever.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$workerScript = Join-Path $root "scripts\run_worker.py"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$restartLog = Join-Path $logDir "worker_restarts.log"

$backoff = 5
while ($true) {
    $start = Get-Date
    & $py $workerScript
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Add-Content $restartLog "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') worker 正常退出，守护结束"
        break
    }
    # 跑了超过 5 分钟才崩 → 视为偶发，退避归零
    if (((Get-Date) - $start).TotalSeconds -gt 300) { $backoff = 5 }
    Add-Content $restartLog "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') worker 异常退出（code=$code），${backoff}s 后重启"
    Start-Sleep -Seconds $backoff
    $backoff = [Math]::Min($backoff * 2, 60)
}
