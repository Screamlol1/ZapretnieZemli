param(
    [string]$Cloudflared = 'cloudflared',
    [ValidateRange(1024,65535)][int]$Port = 8789,
    [ValidateSet('auto','http2','quic')][string]$Protocol = 'auto'
)
$ErrorActionPreference = 'Stop'
$testRoot = Join-Path $PSScriptRoot '.runtime'
$statePath = Join-Path $testRoot 'processes.json'
if (Test-Path -LiteralPath $statePath) { throw 'A test launch is already recorded. Run stop-public-test.ps1 first.' }
$tunnelExecutable = (Get-Command $Cloudflared).Source
$pythonExecutable = (Get-Command python).Source
$nodeExecutable = (Get-Command node).Source
$probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$Port)
try { $probe.Start() } finally { $probe.Stop() }
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$serverPath = Join-Path $PSScriptRoot 'server.py'
$databasePath = Join-Path $testRoot 'test.sqlite'
$configPath = Join-Path $testRoot 'quick-tunnel.yml'
Set-Content -LiteralPath $configPath -Value '{}' -Encoding utf8
$gameProcess = $null
$tunnelProcess = $null
try {
    $gameProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @(('"'+$serverPath+'"'),'--host','127.0.0.1','--port',$Port,'--database',('"'+$databasePath+'"'),'--public-test') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $testRoot 'server.log') -RedirectStandardError (Join-Path $testRoot 'server-errors.log')
    $localUrl = 'http://127.0.0.1:'+ $Port
    $ready = $false
    for ($i=0;$i -lt 40;$i++) {
        if ($gameProcess.HasExited) { throw 'The game server stopped. Check .runtime/server-errors.log.' }
        try { $health=Invoke-RestMethod -Uri ($localUrl+'/api/health') -TimeoutSec 2; if ($health.ok -and $health.publicTest) { $ready=$true; break } } catch {}
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw 'The test server did not become ready.' }
    $tunnelLog = Join-Path $testRoot 'tunnel.log'
    $tunnelProcess = Start-Process -FilePath $tunnelExecutable -ArgumentList @('tunnel','--config',('"'+$configPath+'"'),'--url',$localUrl,'--no-autoupdate','--protocol',$Protocol) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $testRoot 'tunnel-output.log') -RedirectStandardError $tunnelLog
    $publicUrl = $null
    for ($i=0;$i -lt 100;$i++) {
        if ($tunnelProcess.HasExited) { throw 'The tunnel stopped. Check .runtime/tunnel.log.' }
        if (Test-Path -LiteralPath $tunnelLog) {
            $logText=Get-Content -LiteralPath $tunnelLog -Raw
            if ($logText) {
                $match=[regex]::Match($logText,'https://[a-z0-9-]+\.trycloudflare\.com')
                if ($match.Success) { $publicUrl=$match.Value; break }
            }
        }
        Start-Sleep -Milliseconds 300
    }
    if (-not $publicUrl) { throw 'Cloudflare did not issue a URL. Check .runtime/tunnel.log.' }
    $externalReady = $false
    $externalTimer = [System.Diagnostics.Stopwatch]::StartNew()
    while ($externalTimer.Elapsed.TotalSeconds -lt 90) {
        if ($tunnelProcess.HasExited) { throw 'The tunnel stopped. Check .runtime/tunnel.log.' }
        try { $health=Invoke-RestMethod -Uri ($publicUrl+'/api/health') -TimeoutSec 4; if ($health.ok -and $health.publicTest) { $externalReady=$true; break } } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $externalReady) { throw 'The public URL is unreachable. Check .runtime/tunnel.log and network access to Cloudflare.' }
    @{serverPid=$gameProcess.Id;tunnelPid=$tunnelProcess.Id;serverPath=$serverPath;tunnelPath=$tunnelExecutable;databasePath=$databasePath;port=$Port;url=$publicUrl} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
    Write-Output $publicUrl
    Write-Output 'Share the link and the player invitation from the campaign. Keep the computer awake.'
} catch {
    if ($tunnelProcess -and -not $tunnelProcess.HasExited) { Stop-Process -Id $tunnelProcess.Id }
    if ($gameProcess -and -not $gameProcess.HasExited) { Stop-Process -Id $gameProcess.Id }
    throw
}
