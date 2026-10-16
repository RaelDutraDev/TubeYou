$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$runtimeRoot = Join-Path $projectRoot '.runtime'
$pythonExe = Join-Path $projectRoot 'backend\venv\Scripts\python.exe'
$tunnelExe = Join-Path $projectRoot '.tools\cloudflared.exe'
$sessionPath = Join-Path $runtimeRoot 'publico.json'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Prepare backend\venv seguindo o README antes de iniciar.' }
& (Join-Path $projectRoot 'preparar-tunel.ps1')
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
if (Test-Path -LiteralPath $sessionPath) {
    $old = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
    $stillRunning = Get-Process -Id $old.server.id -ErrorAction SilentlyContinue
    if ($stillRunning -and $stillRunning.StartTime.ToUniversalTime().Ticks -eq ([datetimeoffset]$old.server.started).UtcDateTime.Ticks) {
        $oldTunnel = Get-Process -Id $old.tunnel.id -ErrorAction SilentlyContinue
        if (-not $oldTunnel -or $oldTunnel.StartTime.ToUniversalTime().Ticks -ne ([datetimeoffset]$old.tunnel.started).UtcDateTime.Ticks) {
            throw 'O servidor anterior está ligado, mas o túnel foi encerrado. Execute .\parar-publico.ps1 antes de reiniciar.'
        }
        Write-Output ('O teste público já está aberto: ' + $old.url)
        return
    }
}
$server = $null
$tunnel = $null
try {
    $healthReady = $false
    try { $null = Invoke-RestMethod 'http://127.0.0.1:5510/api/health' -TimeoutSec 1; $healthReady = $true } catch {}
    if ($healthReady) { throw 'A porta 5510 já está ocupada. Pare o teste anterior antes de iniciar outro.' }
    $server = Start-Process -FilePath $pythonExe -ArgumentList @('-B', ('"' + (Join-Path $projectRoot 'backend\publico.py') + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot 'servidor.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'servidor.err.log')
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        $server.Refresh()
        if ($server.HasExited) { throw 'O servidor não iniciou. Confira .runtime\servidor.err.log.' }
        try { $null = Invoke-RestMethod 'http://127.0.0.1:5510/api/health' -TimeoutSec 1; $healthReady = $true } catch { Start-Sleep -Milliseconds 250 }
    } while (-not $healthReady -and [DateTime]::UtcNow -lt $deadline)
    if (-not $healthReady) { throw 'O servidor não respondeu no prazo de inicialização.' }
    $configPath = Join-Path $runtimeRoot 'cloudflared.yml'
    'loglevel: info' | Set-Content -LiteralPath $configPath -Encoding utf8
    $arguments = @('tunnel', '--config', ('"' + $configPath + '"'), '--no-autoupdate', '--url', 'http://127.0.0.1:5510', '--protocol', 'http2')
    $tunnel = Start-Process -FilePath $tunnelExe -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeRoot 'tunel.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'tunel.err.log')
    $publicUrl = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(50)
    do {
        $tunnel.Refresh()
        if ($tunnel.HasExited) { throw 'O túnel não iniciou. Confira .runtime\tunel.err.log.' }
        $logText = Get-Content -LiteralPath (Join-Path $runtimeRoot 'tunel.err.log') -Raw -ErrorAction SilentlyContinue
        if ($logText -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $publicUrl = $Matches[0] }
        if (-not $publicUrl) { Start-Sleep -Milliseconds 250 }
    } while (-not $publicUrl -and [DateTime]::UtcNow -lt $deadline)
    if (-not $publicUrl) { throw 'O túnel não forneceu um endereço no prazo esperado.' }
    @{
        url = $publicUrl
        server = @{ id = $server.Id; started = $server.StartTime.ToUniversalTime().ToString('o'); path = $pythonExe }
        tunnel = @{ id = $tunnel.Id; started = $tunnel.StartTime.ToUniversalTime().ToString('o'); path = $tunnelExe }
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $sessionPath -Encoding utf8
    Write-Output ('Site público temporário: ' + $publicUrl)
    Write-Output 'Mantenha o PC ligado. Para encerrar o acesso público: .\parar-publico.ps1'
} catch {
    foreach ($child in @($tunnel, $server)) {
        if ($null -ne $child) {
            $child.Refresh()
            if (-not $child.HasExited) { & taskkill.exe /PID $child.Id /T /F | Out-Null }
        }
    }
    throw
}
