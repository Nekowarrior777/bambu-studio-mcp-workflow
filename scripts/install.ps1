param(
    [string]$PythonExe = 'python',
    [string]$StudioExe = 'C:\Program Files\Bambu Studio\bambu-studio.exe',
    [switch]$RegisterCodex,
    [switch]$InstallSkill
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Source-only installer. No printer operation, firewall/security change or UI
# action is part of installation. Registration/skill installation are opt-in.
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$extensionRoot = Join-Path $repositoryRoot 'tools\unofficial-bambu-mcp'
$safetyRoot = Join-Path $repositoryRoot 'tools\bambu-printer-mcp'
$safetyCommit = 'b3c33f55998b946914273e95fc26d5632bc86e01'
$safetyRemote = 'https://github.com/DMontgomery40/bambu-printer-mcp.git'
$wheelHash = '6ed137707e6ee9e4464256b3d09c97deb3ee596f34b2b1d407dd15898a6cfd70'
$venvPython = Join-Path $extensionRoot '.venv\Scripts\python.exe'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable" }
}

if ($env:OS -ne 'Windows_NT') { throw 'This UI extension requires Windows x64.' }
if (-not (Test-Path -LiteralPath $StudioExe -PathType Leaf)) { throw 'Install Bambu Studio first, or pass -StudioExe with its actual path.' }
$node = (Get-Command node.exe -ErrorAction Stop).Source
$git = (Get-Command git.exe -ErrorAction Stop).Source
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$nodeMajor = & $node -p 'process.versions.node.split(".")[0]'
if ($LASTEXITCODE -ne 0 -or $nodeMajor -ne '24') { throw 'This release is validated with Node.js 24; use that major version.' }
$pythonVersion = & $PythonExe -c 'import sys; print(str(sys.version_info.major)+"."+str(sys.version_info.minor))'
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.14') { throw 'This release is validated with Python 3.14; pass that interpreter as -PythonExe.' }

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Invoke-Checked $PythonExe @('-m','venv',(Join-Path $extensionRoot '.venv'))
}
$downloadRoot = Join-Path $repositoryRoot 'downloads'
New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
Invoke-Checked $venvPython @('-m','pip','download','--no-deps','--only-binary=:all:','--dest',$downloadRoot,'unofficial-bambu-mcp==0.3.0')
$wheel = Join-Path $downloadRoot 'unofficial_bambu_mcp-0.3.0-py3-none-any.whl'
if ((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $wheelHash) {
    throw 'Upstream 0.3.0 wheel SHA256 does not match the reviewed artifact.'
}
Invoke-Checked $venvPython @('-m','pip','install','-r',(Join-Path $extensionRoot 'requirements.lock.txt'),$wheel)
Invoke-Checked $venvPython @('-m','pip','check')
Invoke-Checked $venvPython @((Join-Path $extensionRoot 'apply_windows_patch.py'))

if (Test-Path -LiteralPath $safetyRoot) {
    if (-not (Test-Path -LiteralPath (Join-Path $safetyRoot '.git'))) { throw 'Existing safety-runtime folder is not the expected Git checkout; refusing to replace it.' }
    $existingRemote = & $git -C $safetyRoot remote get-url origin
    if ($LASTEXITCODE -ne 0 -or $existingRemote -ne $safetyRemote) { throw 'Existing safety-runtime origin does not match the pinned upstream.' }
    $existingHead = & $git -C $safetyRoot rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $existingHead -ne $safetyCommit) { throw 'Existing safety-runtime commit differs; refusing to reset it.' }
    $existingChanges = & $git -C $safetyRoot status --porcelain
    if ($LASTEXITCODE -ne 0 -or $existingChanges) { throw 'Existing safety-runtime checkout contains changes; preserve and inspect them before installation.' }
} else {
    Invoke-Checked $git @('clone','--no-checkout','--filter=blob:none',$safetyRemote,$safetyRoot)
    Invoke-Checked $git @('-C',$safetyRoot,'fetch','--depth=1','origin',$safetyCommit)
    Invoke-Checked $git @('-C',$safetyRoot,'checkout','--detach',$safetyCommit)
}
$verifiedHead = & $git -C $safetyRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $verifiedHead -ne $safetyCommit) { throw 'Safety-runtime pin verification failed.' }
Push-Location -LiteralPath $safetyRoot
try {
    Invoke-Checked $npm @('ci')
    Invoke-Checked $npm @('run','build')
} finally { Pop-Location }

$windowsPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
Invoke-Checked $windowsPowerShell @('-NoProfile','-File',(Join-Path $extensionRoot 'local_extension\build_studio_ui.ps1'))

if ($InstallSkill) {
    $skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
    $skillDestination = Join-Path $skillRoot 'bambu-print'
    if (Test-Path -LiteralPath $skillDestination) { throw 'A bambu-print skill already exists; refusing to overwrite it.' }
    New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repositoryRoot 'skills\bambu-print') -Destination $skillDestination -Recurse
}

if ($RegisterCodex) {
    $codex = (Get-Command codex -ErrorAction Stop).Source
    # Capture, do not display, existing configuration: it may contain private data.
    $existing = & $codex mcp get unofficial-bambu --json 2>$null
    if ($LASTEXITCODE -eq 0) { throw 'An unofficial-bambu registration already exists. Back it up and migrate it explicitly; the installer will not overwrite it.' }
    $privateRoot = Join-Path $env:LOCALAPPDATA 'BambuStudioMCPWorkflow'
    $outputRoot = Join-Path $privateRoot 'projects'
    $temporaryRoot = Join-Path $extensionRoot 'tmp'
    New-Item -ItemType Directory -Path $outputRoot,$temporaryRoot -Force | Out-Null
    $studioDirectory = Split-Path -Parent $StudioExe
    $launchEnvironment = [ordered]@{
        BAMBU_STUDIO_EXE = [System.IO.Path]::GetFullPath($StudioExe)
        BAMBU_STUDIO_RESOURCES = Join-Path $studioDirectory 'resources'
        BAMBU_STUDIO_DATA = Join-Path $env:APPDATA 'BambuStudio'
        UBMCP_DIR = $outputRoot
        PYTHONIOENCODING = 'utf-8'
        PYTHONUTF8 = '0'
        TEMP = $temporaryRoot
        TMP = $temporaryRoot
    }
    $registrationArguments = @('mcp','add','unofficial-bambu')
    foreach ($entry in $launchEnvironment.GetEnumerator()) { $registrationArguments += @('--env',($entry.Key + '=' + $entry.Value)) }
    $registrationArguments += @('--',$venvPython,(Join-Path $extensionRoot 'enhanced_server.py'))
    Invoke-Checked $codex $registrationArguments
}
Write-Output 'Local source/runtime setup completed. No printer was contacted and no physical action was performed. Configure private bindings separately. Restart Codex if registration or skill installation was requested.'
