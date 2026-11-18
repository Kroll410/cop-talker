# StalkerTalker setup: Python environment, game folder, mod install, keys file and desktop shortcut.
# Run it through setup.bat. Safe to run again (it only redoes what's missing or changed).
# -NoShortcut: don't touch the desktop (for testing a second copy).
param([switch]$NoShortcut)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root
Add-Type -AssemblyName System.Windows.Forms

function Say($text, $color = 'Gray') { Write-Host $text -ForegroundColor $color }

# 1. Python 3.10 - 3.13 (the libraries are tested with 3.13; a brand-new Python may not have them built yet)
Say "`n[1/6] Python" Cyan
$py = $null
$newest = 0
foreach ($cmd in @('py -3.13', 'py -3.12', 'py -3.11', 'py -3.10', 'python', 'py -3')) {
    try {
        $v = & cmd /c "$cmd -c ""import sys; print(sys.version_info[0]*100+sys.version_info[1])"" 2>nul"
        if ($v) { $newest = [math]::Max($newest, [int]$v) }
        if ($v -and [int]$v -ge 310 -and [int]$v -le 313) { $py = $cmd; break }
    } catch {}
}
if (-not $py) {
    if ($newest -gt 313) {
        Say "Your Python is newer than 3.13. Please also install Python 3.13 (https://www.python.org/downloads/, tick 'Add python.exe to PATH'), then run setup.bat again." Red
    } else {
        Say "Python 3.13 is needed. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run setup.bat again." Red
    }
    exit 1
}
Say "found: $py"

# 2. Libraries in a private environment (.venv)
Say "`n[2/6] Libraries (a few minutes the first time)" Cyan
if (-not (Test-Path '.venv\Scripts\python.exe')) { & cmd /c "$py -m venv .venv" }
& '.venv\Scripts\python.exe' -m pip install --upgrade pip -q
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) { Say "Installing libraries failed (see above)." Red; exit 1 }
Say "ok"

# 3. Game folder
Say "`n[3/6] Game folder" Cyan
$game = ''
$line = Get-Content settings.ini -Encoding UTF8 | Where-Object { $_ -match '^\s*STALKER_DIR\s*=' } | Select-Object -First 1
if ($line) { $game = ($line -split '=', 2)[1].Trim() }
if (-not (Test-Path (Join-Path $game 'bin'))) {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Choose the S.T.A.L.K.E.R.: Call of Pripyat folder (the one with bin, gamedata, resources)'
    if ($dialog.ShowDialog() -ne 'OK') { Say "No folder chosen." Red; exit 1 }
    $game = $dialog.SelectedPath
}
if (-not (Test-Path (Join-Path $game 'bin\xrEngine.exe'))) {
    Say "OpenXRay was not found in $game\bin. StalkerTalker needs it (push-to-talk, actions):" Yellow
    Say "https://github.com/OpenXRay/xray-16/wiki/%5BEN%5D-How-to-install-and-play" Yellow
}
$ini = Get-Content settings.ini -Encoding UTF8
$ini = $ini | ForEach-Object { if ($_ -match '^\s*STALKER_DIR\s*=') { "STALKER_DIR=$game" } else { $_ } }
[System.IO.File]::WriteAllLines((Join-Path $root 'settings.ini'), $ini, (New-Object System.Text.UTF8Encoding $false))
Say "game: $game"

# 4. Mod files into the game
Say "`n[4/6] Game mod" Cyan
& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'install_mod.ps1')

# 5. Keys
Say "`n[5/6] Keys (.env)" Cyan
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env'; Say "created .env from .env.example" }
$envText = Get-Content '.env' -Raw
if ($envText -notmatch '(?m)^GEMINI_API_KEY=\S+') {
    Say "Paste your Gemini key (and the ElevenLabs key and voice IDs) into .env, then save it. Opening it now..." Yellow
    Start-Process notepad.exe (Join-Path $root '.env')
}

# 6. Desktop shortcut
Say "`n[6/6] Desktop shortcut" Cyan
if ($NoShortcut) {
    Say "skipped (-NoShortcut)"
} else {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'StalkerTalker.lnk'))
    $link.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
    $link.Arguments = 'companion\app.py'
    $link.WorkingDirectory = $root
    $link.Description = 'StalkerTalker'
    $link.Save()
    Say "StalkerTalker shortcut is on the desktop."
}

# Optional: voice samples for cloning
$db = Get-ChildItem -Path $game -Recurse -Filter 'xukrainian.db' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($db -and -not (Test-Path 'samples\human_01_ukr.mp3')) {
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "Make voice samples for ElevenLabs cloning from the game's Ukrainian voiceover now?`n($($db.FullName))",
        'StalkerTalker', 'YesNo')
    if ($answer -eq 'Yes') {
        & '.venv\Scripts\python.exe' tools\make_voice_samples.py $db.FullName samples
        Say "Samples are in $root\samples (see README, step 3)." Green
    }
}
Say "`nDone. Start the game, then StalkerTalker from the desktop." Green
