$ErrorActionPreference = 'Stop'
$toolsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.tools'))
New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
$tunnelExe = Join-Path $toolsRoot 'cloudflared.exe'
$manifestPath = Join-Path $toolsRoot 'cloudflared.json'
if ((Test-Path -LiteralPath $tunnelExe) -and (Test-Path -LiteralPath $manifestPath)) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ((Get-FileHash -LiteralPath $tunnelExe -Algorithm SHA256).Hash.ToLower() -eq $manifest.sha256) {
        Write-Output 'Cloudflared já está preparado e seu hash confere.'
        return
    }
    throw 'O hash do cloudflared local não corresponde ao manifesto. Confira a pasta .tools antes de continuar.'
}
$headers = @{ 'User-Agent' = 'TubeYou-Setup'; 'Accept' = 'application/vnd.github+json' }
$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/cloudflare/cloudflared/releases/latest' -Headers $headers
$asset = @($release.assets | Where-Object { $_.name -eq 'cloudflared-windows-amd64.exe' })
if ($asset.Count -ne 1 -or $asset[0].digest -notmatch '^sha256:([0-9a-f]{64})$') {
    throw 'Não foi possível obter o checksum oficial do cloudflared.'
}
$expectedHash = $Matches[1]
if ($asset[0].browser_download_url -notlike 'https://github.com/cloudflare/cloudflared/releases/download/*') {
    throw 'O endereço do executável não é o repositório oficial esperado.'
}
$temporaryDownload = Join-Path $toolsRoot 'cloudflared.download'
Invoke-WebRequest -Uri $asset[0].browser_download_url -OutFile $temporaryDownload
if ((Get-FileHash -LiteralPath $temporaryDownload -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) {
    throw 'O checksum do arquivo baixado não confere. O executável não será iniciado.'
}
Move-Item -LiteralPath $temporaryDownload -Destination $tunnelExe -Force
@{ version = $release.tag_name; sha256 = $expectedHash } | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output ('Cloudflared oficial preparado: ' + $release.tag_name)
