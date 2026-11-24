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
# Our item sections: the #include line comes out of external.ltx, and the file itself goes if install_mod.ps1 made it
# and nothing else changed it since. A save where someone still carries the Vova Vist machine gun needs them: load
# such a save only with the mod installed.
Remove-Item "$game\gamedata\configs\talker_items.ltx" -ErrorAction SilentlyContinue
Get-ChildItem "$game\gamedata\configs\text\*\talker_items.xml" -ErrorAction SilentlyContinue | Remove-Item
$ext = "$game\gamedata\configs\external.ltx"
$ours = "$game\talker\external_ltx_ours.txt"
if (Test-Path $ext) {
    $latin = [Text.Encoding]::GetEncoding(28591)
    $text = [IO.File]::ReadAllText($ext, $latin)
    $text = [Regex]::Replace($text, '(?m)^[ \t]*#include[ \t]+"talker_items\.ltx"[ \t]*\r?\n?', '')
    [IO.File]::WriteAllText($ext, $text, $latin)
    if ((Test-Path $ours) -and (Get-FileHash $ext -Algorithm SHA256).Hash -eq (Get-Content $ours -Raw).Trim()) {
        Remove-Item $ext
    }
}
Remove-Item $ours -ErrorAction SilentlyContinue
Write-Host "StalkerTalker scripts removed from $game"
