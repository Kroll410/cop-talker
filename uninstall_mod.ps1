# Removes the StalkerTalker scripts from the game (the game goes back to its original scripts).
$game = 'C:\Games\S.T.A.L.K.E.R. Call of Pripyat'
$line = Get-Content (Join-Path $PSScriptRoot 'settings.ini') -Encoding UTF8 -ErrorAction SilentlyContinue |
    Where-Object { $_ -match '^\s*STALKER_DIR\s*=' } | Select-Object -First 1
if ($line) { $game = ($line -split '=', 2)[1].Trim() }
foreach ($f in 'talker_bridge.script', 'bind_stalker.script', 'xr_motivator.script', 'xr_combat_ignore.script', 'sim_squad_scripted.script', 'sim_squad_actions.script', 'xr_reach_task.script') {
    Remove-Item "$game\gamedata\scripts\$f" -ErrorAction SilentlyContinue
}
foreach ($f in 'talker_follow.ltx', 'talker.ltx') {
    Remove-Item "$game\gamedata\configs\scripts\$f" -ErrorAction SilentlyContinue
}
Remove-Item "$game\gamedata\sounds\talker" -Recurse -ErrorAction SilentlyContinue
Write-Host "StalkerTalker scripts removed from $game"
