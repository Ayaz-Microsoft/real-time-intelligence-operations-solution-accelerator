<#
.SYNOPSIS
    Removes Microsoft Fabric workspace for the Real-Time Intelligence Operations Solution Accelerator.

.DESCRIPTION
    Orchestrates the removal of RTI workspace from Microsoft Fabric including:
    • Workspace lookup and verification
    • Safe deletion with confirmation prompts
    • Comprehensive error handling and user guidance

.PARAMETER SkipPythonVirtualEnvironment
    Use system Python directly instead of creating virtual environment.

.PARAMETER SkipPythonDependencies
    Skip installing Python dependencies (assume pre-installed).

.PARAMETER SkipPipUpgrade
    Skip upgrading pip to latest version.

.EXAMPLE
    .\Run-RemoveFabricRtiPythonScript.ps1
    
.EXAMPLE
    .\Run-RemoveFabricRtiPythonScript.ps1 -SkipPythonVirtualEnvironment -SkipPythonDependencies

.NOTES
    Prerequisites: Azure CLI (logged in), PowerShell 7+, Python 3.9+, appropriate Fabric workspace permissions
    
    Required Environment Variables:
    - SOLUTION_SUFFIX: Suffix to append to default workspace name
    
    Optional Environment Variables:
    - FABRIC_WORKSPACE_NAME: Name of the Fabric workspace (uses default if not set)
    - FABRIC_WORKSPACE_ID: ID of the Fabric workspace (GUID, overrides name-based lookup)
#>

param(
    [Parameter(Mandatory = $false, HelpMessage = "Skip creating and using Python virtual environment (use system Python directly)")]
    [switch]$SkipPythonVirtualEnvironment,
    
    [Parameter(Mandatory = $false, HelpMessage = "Skip installing Python dependencies from requirements.txt (assume dependencies are already installed)")]
    [switch]$SkipPythonDependencies,
    
    [Parameter(Mandatory = $false, HelpMessage = "Skip upgrading pip to the latest version")]
    [switch]$SkipPipUpgrade
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Helper function for colored output
function Write-Info { param([string]$Message) Write-Host $Message -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Warning { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Error { param([string]$Message) Write-Host $Message -ForegroundColor Red }

# Helper function to find Python executable
function Get-PythonCommand {
    $pythonCommands = @("python3", "python")
    foreach ($cmd in $pythonCommands) {
        try {
            $null = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0) { return $cmd }
        }
        catch { }
    }
    throw "Python is not installed or not available in PATH. Please install Python 3.9+ and try again."
}

# Helper function to setup Python environment
function Initialize-PythonEnvironment {
    param(
        [string]$RepoRoot,
        [bool]$SkipVirtualEnv,
        [bool]$SkipDependencies,
        [bool]$SkipPipUpgrade,
        [string]$RequirementsPath
    )
    
    $pythonCmd = Get-PythonCommand
    Write-Success "Python found: $pythonCmd"
    
    if ($SkipVirtualEnv) {
        Write-Info "Skipping Python virtual environment - using system Python"
        $pythonExec = $pythonCmd
    }
    else {
        Write-Warning "Setting up Python virtual environment..."
        $venvPath = Join-Path $RepoRoot ".venv"
        
        if (-not (Test-Path $venvPath)) {
            & $pythonCmd -m venv "$venvPath"
            if ($LASTEXITCODE -ne 0) { throw "Failed to create Python virtual environment." }
        }
        
        # Activate virtual environment
        $activateScript = if ($IsWindows -or $env:OS -eq "Windows_NT") {
            Join-Path $venvPath "Scripts\Activate.ps1"
        }
        else {
            Join-Path $venvPath "bin\activate.ps1"
        }
        
        if (Test-Path $activateScript) { & $activateScript } 
        else { throw "Virtual environment activation script not found at '$activateScript'." }
        
        $pythonExec = if ($IsWindows -or $env:OS -eq "Windows_NT") {
            Join-Path $venvPath "Scripts\python.exe"
        }
        else {
            Join-Path $venvPath "bin\python3"
        }
    }
    
    # Upgrade pip if not skipped
    if (-not $SkipPipUpgrade) {
        Write-Warning "Upgrading pip..."
        & $pythonExec -m pip install --upgrade pip --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Warning: Failed to upgrade pip, continuing with existing version..."
        }
    }
    else {
        Write-Info "Skipping pip upgrade"
    }
    
    # Install dependencies if not skipped
    if (-not $SkipDependencies) {
        Write-Warning "Installing requirements..."
        if (-not (Test-Path $RequirementsPath)) {
            throw "requirements.txt not found at: $RequirementsPath"
        }
        & $pythonExec -m pip install -r "$RequirementsPath" --quiet
        if ($LASTEXITCODE -ne 0) { throw "Failed to install Python dependencies." }
    }
    else {
        Write-Info "Skipping Python dependencies installation"
    }
    
    return $pythonExec
}

# Display configuration
Write-Error "Starting Microsoft Fabric workspace removal script..."

try {
    # Calculate paths - script is now in utils, but fabric scripts are in ../fabric
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $FabricScriptsDir = Join-Path (Split-Path -Parent $ScriptDir) "fabric"
    $RepoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ScriptDir))
    $RequirementsPath = Join-Path $RepoRoot "requirements.txt"
    
    # Initialize Python environment
    $pythonExec = Initialize-PythonEnvironment -RepoRoot $RepoRoot -SkipVirtualEnv:$SkipPythonVirtualEnvironment -SkipDependencies:$SkipPythonDependencies -SkipPipUpgrade:$SkipPipUpgrade -RequirementsPath $RequirementsPath

    # Execute Python removal script - change to fabric scripts directory
    Push-Location $FabricScriptsDir
    Write-Warning "Starting Fabric workspace removal..."
    
    # Execute Python script (no arguments needed - uses environment variables)
    & $pythonExec -u remove_fabric_rti.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "✅ Fabric workspace removal completed successfully!"
    }
    else {
        throw "Python script execution failed with exit code: $LASTEXITCODE"
    }
}
catch {
    Write-Error "❌ Removal failed: $($_.Exception.Message)"
    Write-Host ""
    Write-Warning "Troubleshooting tips:"
    @(
        "1. Ensure you are logged in to Azure CLI: az login",
        "2. Verify you have Admin permissions on the workspace to delete", 
        "3. Ensure the workspace name or ID is correct and accessible"
    ) | ForEach-Object { Write-Host $_ -ForegroundColor White }
    exit 1
}
finally {
    # Cleanup
    if ($env:VIRTUAL_ENV -and (Get-Command deactivate -ErrorAction SilentlyContinue)) {
        deactivate
    }
    if (Get-Location -Stack -ErrorAction SilentlyContinue) {
        Pop-Location
    }
}