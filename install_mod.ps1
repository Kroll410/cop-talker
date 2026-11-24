# Copies the StalkerTalker scripts, configs and sounds into the game and creates the bridge folder.
# The game folder is STALKER_DIR in settings.ini. Re-run after changing anything in mod\. Remove with uninstall_mod.ps1
$ErrorActionPreference = 'Stop'
$game = 'C:\Games\S.T.A.L.K.E.R. Call of Pripyat'
$ini = Join-Path $PSScriptRoot 'settings.ini'
if (-not (Test-Path $ini)) { Copy-Item (Join-Path $PSScriptRoot 'settings.example.ini') $ini }  # your copy, not in git
$line = Get-Content $ini -Encoding UTF8 -ErrorAction SilentlyContinue |
    Where-Object { $_ -match '^\s*STALKER_DIR\s*=' } | Select-Object -First 1
if ($line) { $game = ($line -split '=', 2)[1].Trim() }
if (-not (Test-Path (Join-Path $game 'gamedata')) -and -not (Test-Path (Join-Path $game 'bin'))) {
    throw "Game not found in '$game'. Set STALKER_DIR in settings.ini to your S.T.A.L.K.E.R. Call of Pripyat folder."
}
$src = Join-Path $PSScriptRoot 'mod\gamedata'
New-Item -ItemType Directory -Force "$game\gamedata\scripts", "$game\gamedata\configs\scripts", "$game\gamedata\sounds\talker", "$game\talker" | Out-Null
Copy-Item "$src\scripts\*.script" "$game\gamedata\scripts\" -Force
Copy-Item "$src\configs\scripts\*.ltx" "$game\gamedata\configs\scripts\" -Force
# silent clips that move NPC mouths, the 62 reward shout. A running game keeps them open: then they're left as they
# are (they rarely change) and the rest still goes in
try { Copy-Item "$src\sounds\talker\*.ogg" "$game\gamedata\sounds\talker\" -Force -ErrorAction Stop }
catch { Write-Output "Sounds not updated (the game has them open; close it and reinstall if they changed)" }

# Our own item sections (the Vova Vist reward's machine gun) and their names. The game reads every
# configs\text\<language>\*.xml by itself; the sections need one #include line in configs\external.ltx, the file the
# game keeps for that. If gamedata has no external.ltx yet, the game's own (patched) one is copied out of its archives
# first, so nothing in it is lost. Running this again adds nothing twice.
Copy-Item "$src\configs\talker_items.ltx" "$game\gamedata\configs\" -Force
foreach ($lang in Get-ChildItem "$src\configs\text" -Directory) {
    New-Item -ItemType Directory -Force "$game\gamedata\configs\text\$($lang.Name)" | Out-Null
    Copy-Item "$($lang.FullName)\talker_items.xml" "$game\gamedata\configs\text\$($lang.Name)\" -Force
}
$ext = "$game\gamedata\configs\external.ltx"
$latin = [Text.Encoding]::GetEncoding(28591)  # byte for byte: the file is cp1251, we only add an ASCII line
if (-not (Test-Path $ext)) {
    $py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { $py = 'python' }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('talker_ext_' + [Guid]::NewGuid().ToString('N'))
    # the newest archive that has it wins, as in the game: patches (last name first), then configs.db
    $dbs = @(Get-ChildItem "$game\patches\*.db" -ErrorAction SilentlyContinue | Sort-Object Name -Descending) +
           @(Get-Item "$game\resources\configs.db" -ErrorAction SilentlyContinue)
    foreach ($db in $dbs) {
        try { & $py -I (Join-Path $PSScriptRoot 'tools\xdb_unpack.py') $db.FullName $tmp 'configs\external.ltx' *> $null } catch { }
        if (Test-Path "$tmp\configs\external.ltx") { break }
    }
    if (Test-Path "$tmp\configs\external.ltx") {
        Copy-Item "$tmp\configs\external.ltx" $ext
        $hash = (Get-FileHash $ext -Algorithm SHA256).Hash  # uninstall deletes it only if it's still just that copy
        Set-Content "$game\talker\external_ltx_ours.txt" $hash -Encoding ASCII
    }
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path $ext) {
    $text = [IO.File]::ReadAllText($ext, $latin)
    if ($text -notmatch '(?m)^\s*#include\s+"talker_items\.ltx"') {
        [IO.File]::WriteAllText($ext, "#include `"talker_items.ltx`"`r`n" + $text, $latin)  # first line: before any section
    }
} else {
    Write-Warning "Couldn't copy the game's configs\external.ltx (no Python? run setup.bat first). The Vova Vist reward won't work until you run this again."
}
Write-Host "Installed StalkerTalker into $game"
