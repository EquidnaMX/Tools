param(
    [string]$VenvPath = ".venv"
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Command $($Arguments -join ' ')"
    }
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} else {
    throw "Python was not found in PATH."
}

Write-Host "Using Python launcher: $python"

if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment at $VenvPath"
    Invoke-Checked -Command $python -Arguments @("-m", "venv", $VenvPath)
}

$activateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    throw "Could not find activation script at $activateScript"
}

. $activateScript

Invoke-Checked -Command "python" -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")

if (Test-Path "requirements-dev.txt") {
    Invoke-Checked -Command "python" -Arguments @("-m", "pip", "install", "-r", "requirements-dev.txt")
}

Invoke-Checked -Command "python" -Arguments @("-m", "pip", "install", "-e", ".")

Write-Host "Installation finished."
Write-Host "Run: .\.venv\Scripts\Activate.ps1 ; tools --help"
