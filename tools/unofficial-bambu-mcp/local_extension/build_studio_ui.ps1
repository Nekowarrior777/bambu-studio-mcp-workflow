param([switch]$WithFixture)
$ErrorActionPreference = 'Stop'
$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$compiler = Join-Path $framework 'csc.exe'
$source = Join-Path $PSScriptRoot 'StudioUi.cs'
$references = @(
    (Join-Path $framework 'System.Web.Extensions.dll'),
    (Join-Path $framework 'WPF\WindowsBase.dll'),
    (Join-Path $framework 'WPF\UIAutomationClient.dll'),
    (Join-Path $framework 'WPF\UIAutomationTypes.dll'),
    (Join-Path $framework 'System.Windows.Forms.dll'),
    (Join-Path $framework 'System.Drawing.dll')
)
foreach ($required in @($compiler, $source) + $references) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required build file: $required" }
}
$referenceArgs = $references | ForEach-Object { '/reference:' + $_ }
$production = Join-Path $PSScriptRoot 'StudioUi.exe'
& $compiler /nologo /target:exe /platform:x64 /optimize+ /out:$production @referenceArgs $source
if ($LASTEXITCODE -ne 0) { throw "StudioUi build failed ($LASTEXITCODE)." }
if ($WithFixture) {
    $fixture = Join-Path $PSScriptRoot 'StudioUiFixture.exe'
    & $compiler /nologo /target:exe /platform:x64 /optimize+ /define:TEST /out:$fixture @referenceArgs $source
    if ($LASTEXITCODE -ne 0) { throw "StudioUi fixture build failed ($LASTEXITCODE)." }
}
[PSCustomObject]@{
    executable = $production
    bytes = (Get-Item -LiteralPath $production).Length
    sha256 = (Get-FileHash -LiteralPath $production -Algorithm SHA256).Hash.ToLowerInvariant()
    fixture = if ($WithFixture) { $fixture } else { $null }
} | ConvertTo-Json
