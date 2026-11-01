$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot '.runtime/processes.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No recorded test launch.'; exit }
$record = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
foreach ($entry in @(@{id=$record.tunnelPid;path=$record.tunnelPath;flag='--url'},@{id=$record.serverPid;path=$record.serverPath;flag='--public-test'})) {
    $processInfo = Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$entry.id)
    if ($processInfo) {
        if (-not $processInfo.CommandLine.Contains($entry.path) -or -not $processInfo.CommandLine.Contains($entry.flag)) { throw 'Process identity changed; stop it manually after inspection.' }
        Stop-Process -Id $entry.id
    }
}
Remove-Item -LiteralPath $statePath
Write-Output 'Test sharing stopped. Campaign data is retained in .runtime/test.sqlite.'
