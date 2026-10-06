# Build the Windows app folder and installer.  Run from the repository root in a Python 3.12 environment
# with the project installed (pip install -e .[dev]).  Requires Inno Setup 6 (installed automatically via
# Chocolatey when missing on CI).
$ErrorActionPreference = "Stop"
$version = (python -c "import stressaero; print(stressaero.__version__)").Trim()

Write-Host "== PyInstaller build ($version)"
pyinstaller --noconfirm --clean packaging\stressaero.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "== Frozen self-test"
$out = Join-Path $env:TEMP "stressaero-selftest.txt"
if (Test-Path $out) { Remove-Item $out }
$p = Start-Process -FilePath "dist\StressAero\StressAero.exe" -ArgumentList "--selftest", "--selftest-out", "`"$out`"" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "self-test exit code $($p.ExitCode)" }
$result = Get-Content $out -Raw
Write-Host $result
if (-not $result.StartsWith("SELFTEST OK")) { throw "self-test failed: $result" }

Write-Host "== Inno Setup"
$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = $candidate }
}
if (-not $iscc) {
    choco install innosetup -y --no-progress
    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
}
& $iscc "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Get-ChildItem dist\StressAero-Setup-*.exe | ForEach-Object { Write-Host "Installer: $($_.FullName) ($([math]::Round($_.Length / 1MB)) MB)" }
