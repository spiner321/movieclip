$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$url = 'http://127.0.0.1:8765/'

function Test-Studio {
    try {
        $state = Invoke-RestMethod -Uri ($url + 'api/health') -TimeoutSec 1
        return $state.app -eq 'MovieClip'
    } catch {
        return $false
    }
}

try {
    if (-not (Test-Studio)) {
        $arguments = @('--cd', ('"{0}"' -f $root), 'python3', '-B', 'movieclip_studio.py')
        $engine = Start-Process -FilePath 'wsl.exe' -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $deadline = (Get-Date).AddSeconds(35)
        while (-not (Test-Studio)) {
            if ($engine.HasExited -or (Get-Date) -gt $deadline) {
                throw 'The MovieClip engine could not start. Check that WSL and python3 are available, and that port 8765 is free.'
            }
            Start-Sleep -Milliseconds 300
        }
    }
    $browserPaths = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $browser = $browserPaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($browser) {
        Start-Process -FilePath $browser -ArgumentList "--app=$url"
    } else {
        Start-Process $url
    }
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
}
