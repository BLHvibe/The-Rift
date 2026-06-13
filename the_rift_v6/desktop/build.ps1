# Build TheRiftV6.exe — run from the_rift_v6/desktop after `npm run build`.
# Bundles the web app + the v5 data package (UI-free Riot/LCU logic the
# /local sidecar endpoints import).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$v5 = Resolve-Path (Join-Path $here "..\..\the_rift")

# Fresh web bundle
if (Test-Path web) { Remove-Item -Recurse -Force web }
Copy-Item -Recurse ..\app\dist web

pyinstaller --noconfirm --onefile --noconsole --name TheRiftV6 `
  --add-data "web;web" `
  --add-data "$v5\data\config.json;data" `
  --paths "$v5" `
  --hidden-import data.config `
  --hidden-import data.rift_api `
  --hidden-import data.rankings_refresh_api `
  --hidden-import data.fetch_ranks.riot `
  --hidden-import data.fetch_ranks.scoring `
  --hidden-import data.fetch_ranks.scouting `
  --hidden-import data.fetch_ranks.api_writer `
  --hidden-import data.fetch_ranks.constants `
  --hidden-import local_api `
  --collect-all webview --collect-all clr_loader --collect-all pythonnet `
  launcher.py

Write-Host "`nSmoke test:"
$p = Start-Process dist\TheRiftV6.exe -ArgumentList "--headless" -PassThru -Wait
Write-Host "ExitCode: $($p.ExitCode)  (0 = server+bundle+live proxy OK)"
