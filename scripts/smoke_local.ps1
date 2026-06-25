param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$WebDir = (Join-Path $PSScriptRoot "..\web"),
    [string]$Email = $env:NOTEGEN_SMOKE_EMAIL,
    [string]$Password = $env:NOTEGEN_SMOKE_PASSWORD,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Continue"
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Pass([string]$Message) {
    Write-Host "  OK   $Message" -ForegroundColor Green
}

function Warn([string]$Message) {
    $warnings.Add($Message) | Out-Null
    Write-Host "  WARN $Message" -ForegroundColor Yellow
}

function Fail([string]$Message) {
    $failures.Add($Message) | Out-Null
    Write-Host "  FAIL $Message" -ForegroundColor Red
}

function Invoke-SmokeCheck([string]$Name, [scriptblock]$Check) {
    Write-Host ""
    Write-Host "== $Name =="
    try {
        & $Check
    } catch {
        Fail "$Name`: $($_.Exception.Message)"
    }
}

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        throw $Message
    }
}

Write-Host "NoteGen local smoke"
Write-Host "API: $ApiBase"
Write-Host "Web: $WebDir"

Invoke-SmokeCheck "Redis TCP" {
    $redisOnline = Test-NetConnection -ComputerName "127.0.0.1" -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue
    Assert-True $redisOnline "127.0.0.1:6379 is not reachable. Start it with: docker compose up -d redis"
    Pass "127.0.0.1:6379 accepts TCP connections"
}

Invoke-SmokeCheck "API health" {
    $health = Invoke-RestMethod -Uri "$ApiBase/api/health" -Method Get -TimeoutSec 8
    Assert-True ($null -ne $health) "empty health response"
    Assert-True ([bool]$health.redis) "health.redis is false"
    Assert-True (-not [bool]$health.disk.low) "disk.low is true"
    Pass "redis=$($health.redis), queue_depth=$($health.queue_depth), disk.low=$($health.disk.low)"
}

Invoke-SmokeCheck "Worker process" {
    $workers = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match "scripts[\\/]+run_worker\.py" }
    $workerIds = @($workers | ForEach-Object { $_.ProcessId })
    $rootWorkers = @($workers | Where-Object { $workerIds -notcontains $_.ParentProcessId })
    if (-not $rootWorkers) {
        Warn "no run_worker.py process found. Start one worker with: .\.venv\Scripts\python.exe scripts\run_worker.py"
        return
    }
    Assert-True ($rootWorkers.Count -eq 1) "expected exactly one worker, found $($rootWorkers.Count)"
    Pass "one run_worker.py process is running (pid=$($rootWorkers[0].ProcessId))"
}

Invoke-SmokeCheck "Public notes API" {
    $notes = Invoke-RestMethod -Uri "$ApiBase/api/notes/public" -Method Get -TimeoutSec 8
    Assert-True ($notes -is [array]) "public notes response is not an array"
    Pass "public notes endpoint returned $($notes.Count) item(s)"
}

Invoke-SmokeCheck "Authenticated session" {
    if ([string]::IsNullOrWhiteSpace($Email) -or [string]::IsNullOrWhiteSpace($Password)) {
        Warn "skip login. Set NOTEGEN_SMOKE_EMAIL and NOTEGEN_SMOKE_PASSWORD, or pass -Email/-Password"
        return
    }

    $body = @{ email = $Email; password = $Password } | ConvertTo-Json
    $login = Invoke-RestMethod `
        -Uri "$ApiBase/api/auth/login" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -SessionVariable session `
        -TimeoutSec 8
    Assert-True ($null -ne $login.id) "login response has no user id"

    $mine = Invoke-RestMethod -Uri "$ApiBase/api/notes/mine" -Method Get -WebSession $session -TimeoutSec 8
    Assert-True ($mine -is [array]) "private notes response is not an array"
    Pass "login ok for $Email; private notes returned $($mine.Count) item(s)"
}

Invoke-SmokeCheck "DOCX export" {
    $body = @{
        filename = "smoke.docx"
        markdown = "# Smoke Test`n`n- DOCX export endpoint is available."
    } | ConvertTo-Json
    $response = Invoke-WebRequest `
        -UseBasicParsing `
        -Uri "$ApiBase/api/export/docx" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 15
    $contentLength = $response.Content.Length
    Assert-True ($response.StatusCode -eq 200) "expected 200, got $($response.StatusCode)"
    Assert-True ($contentLength -gt 1000) "DOCX response is unexpectedly small: $contentLength bytes"
    Pass "DOCX export returned $contentLength bytes"
}

Invoke-SmokeCheck "Web production build" {
    if ($SkipBuild) {
        Warn "skip web build because -SkipBuild was passed"
        return
    }
    Assert-True (Test-Path $WebDir) "web directory not found: $WebDir"
    Push-Location $WebDir
    try {
        npm run build
        Assert-True ($LASTEXITCODE -eq 0) "npm run build exited with $LASTEXITCODE"
        Pass "npm run build completed"
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "== Summary =="
Write-Host "Failures: $($failures.Count)"
Write-Host "Warnings: $($warnings.Count)"

if ($warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Warnings:"
    foreach ($warning in $warnings) {
        Write-Host "  - $warning"
    }
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Failures:"
    foreach ($failure in $failures) {
        Write-Host "  - $failure"
    }
    exit 1
}

exit 0
