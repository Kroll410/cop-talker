# Copies the StalkerTalker scripts, configs and sounds into the game and creates the bridge folder.
# The game folder is STALKER_DIR in settings.ini. Re-run after changing anything in mod\. Remove with uninstall_mod.ps1
$ErrorActionPreference = 'Stop'
$game = 'C:\Games\S.T.A.L.K.E.R. Call of Pripyat'
$line = Get-Content (Join-Path $PSScriptRoot 'settings.ini') -Encoding UTF8 -ErrorAction SilentlyContinue |
    Where-Object { $_ -match '^\s*STALKER_DIR\s*=' } | Select-Object -First 1
if ($line) { $game = ($line -split '=', 2)[1].Trim() }
if (-not (Test-Path (Join-Path $game 'gamedata')) -and -not (Test-Path (Join-Path $game 'bin'))) {
    throw "Game not found in '$game'. Set STALKER_DIR in settings.ini to your S.T.A.L.K.E.R. Call of Pripyat folder."
}
$src = Join-Path $PSScriptRoot 'mod\gamedata'
New-Item -ItemType Directory -Force "$game\gamedata\scripts", "$game\gamedata\configs\scripts", "$game\gamedata\sounds\talker", "$game\talker" | Out-Null
Copy-Item "$src\scripts\*.script" "$game\gamedata\scripts\" -Force
Copy-Item "$src\configs\scripts\*.ltx" "$game\gamedata\configs\scripts\" -Force
Copy-Item "$src\sounds\talker\*.ogg" "$game\gamedata\sounds\talker\" -Force  # silent clips that move NPC mouths
Write-Host "Installed StalkerTalker into $game"
