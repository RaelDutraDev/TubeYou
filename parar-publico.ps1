$ErrorActionPreference = 'Stop'
$sessionPath = Join-Path $PSScriptRoot '.runtime\publico.json'
if (-not (Test-Path -LiteralPath $sessionPath)) { Write-Output 'Nenhum teste público registrado.'; return }
$session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
$expectedPaths = @{
    server = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'backend\venv\Scripts\python.exe'))
    tunnel = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.tools\cloudflared.exe'))
}
foreach ($kind in @('tunnel', 'server')) {
    $entry = $session.$kind
    if ([IO.Path]::GetFullPath($entry.path) -ne $expectedPaths[$kind]) { throw 'Caminho de processo fora do projeto.' }
    $process = Get-Process -Id ([int]$entry.id) -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    if ($process.StartTime.ToUniversalTime().Ticks -ne ([datetimeoffset]$entry.started).UtcDateTime.Ticks -or $process.Path -ne $expectedPaths[$kind]) {
        throw 'O identificador foi reutilizado por outro processo. Nada será encerrado.'
    }
    & taskkill.exe /PID $process.Id /T /F | Out-Null
}
Write-Output 'Teste público encerrado. Os servidores locais das portas 5000/5500 foram preservados.'
