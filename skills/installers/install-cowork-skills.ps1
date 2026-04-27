<#
.SYNOPSIS
  Install graphify + autotrigger skills into Cowork (and Claude Code as a bonus).

.DESCRIPTION
  Copies the SKILL.md folders into Cowork's skills directory so /graphify and
  /autotrigger become available as slash-commands inside Cowork. Also drops
  copies into the user-level Claude Code skills path so they work in both apps.

  Cowork's skills live under a versioned plugin path:
    %LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\
        local-agent-mode-sessions\skills-plugin\*\*\skills\

  This script auto-discovers the active plugin/version directory by picking
  the most recently modified one.

.NOTES
  Run from the `skills/installers` directory so the relative ../graphify
  and ../autotrigger paths resolve. Or just double-click install-cowork-skills.bat
  which calls this with the right working directory.
#>

[CmdletBinding()]
param(
  [switch]$DryRun,
  [switch]$ClaudeCodeOnly
)

$ErrorActionPreference = 'Stop'

function Write-Step {
  param([string]$msg, [string]$color = 'Cyan')
  Write-Host "==> $msg" -ForegroundColor $color
}

# Resolve script directory and source skill folders
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillsRoot = Split-Path -Parent $scriptDir
$sourceFolders = @(
  @{ Name = 'graphify';    Path = Join-Path $skillsRoot 'graphify' }
  @{ Name = 'autotrigger'; Path = Join-Path $skillsRoot 'autotrigger' }
)

foreach ($src in $sourceFolders) {
  if (-not (Test-Path (Join-Path $src.Path 'SKILL.md'))) {
    Write-Error "Source skill folder missing SKILL.md: $($src.Path)"
    exit 1
  }
}

# --- Target 1: Cowork ---
$coworkTarget = $null
if (-not $ClaudeCodeOnly) {
  Write-Step 'Locating Cowork skills directory...'
  $coworkBase = Join-Path $env:LOCALAPPDATA 'Packages'
  $coworkPattern = Join-Path $coworkBase 'Claude_*\LocalCache\Roaming\Claude\local-agent-mode-sessions\skills-plugin\*\*\skills'
  $candidates = Get-ChildItem -Path $coworkPattern -Directory -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending
  if ($candidates) {
    $coworkTarget = $candidates[0].FullName
    Write-Host "    found: $coworkTarget" -ForegroundColor DarkGray
  } else {
    Write-Warning "Cowork skills directory not found. Skipping Cowork install. Use -ClaudeCodeOnly to suppress this warning."
  }
}

# --- Target 2: Claude Code (user-level) ---
$claudeTarget = Join-Path $env:USERPROFILE '.claude\skills'
if (-not (Test-Path $claudeTarget)) {
  if (-not $DryRun) {
    New-Item -ItemType Directory -Path $claudeTarget -Force | Out-Null
  }
}
Write-Host "    Claude Code target: $claudeTarget" -ForegroundColor DarkGray

# --- Copy ---
$targets = @()
if ($coworkTarget) { $targets += $coworkTarget }
$targets += $claudeTarget

foreach ($target in $targets) {
  Write-Step "Installing into: $target"
  foreach ($src in $sourceFolders) {
    $dest = Join-Path $target $src.Name
    if ($DryRun) {
      Write-Host "    [dry-run] would copy $($src.Path) -> $dest"
      continue
    }
    if (Test-Path $dest) {
      Write-Host "    refreshing $($src.Name)"
      Remove-Item -Recurse -Force $dest
    } else {
      Write-Host "    installing $($src.Name)"
    }
    Copy-Item -Recurse -Path $src.Path -Destination $dest
  }
}

Write-Step 'Done.' Green
Write-Host ''
Write-Host 'Restart Cowork to pick up the new skills.'
Write-Host 'After restart, type /graphify or /autotrigger in Cowork to verify.'
Write-Host ''

if (-not $env:CI) {
  Write-Host 'Press any key to close...' -ForegroundColor DarkGray
  $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
}
