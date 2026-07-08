<#
.SYNOPSIS
    Installs this repo's skill library (.github/skills/, .github/prompts/,
    .cursor/rules/, AGENTS.md) into an existing target project directory.

.DESCRIPTION
    Not a package-manager-style installer: no version pinning, no network
    fetch. Run this from inside a clone of context-engineering-oss, pointed
    at a separate target project directory.

.PARAMETER TargetPath
    Required. Path to an existing target project directory.

.PARAMETER InitProject
    Also scaffold context-config.yaml (if absent) and
    starter_kit/project_guidelines/.pointer.md (if absent).

.PARAMETER DryRun
    Print what would be done without writing anything.
#>
[CmdletBinding()]
param(
    [string]$TargetPath = "",
    [switch]$InitProject,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($TargetPath)) {
    Write-Error "-TargetPath <dir> is required."
    exit 1
}

if (-not (Test-Path -LiteralPath $TargetPath -PathType Container)) {
    Write-Error "Target directory does not exist: $TargetPath"
    exit 1
}

$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$TargetPath = (Resolve-Path -LiteralPath $TargetPath).Path

if ($TargetPath -eq $SourceRoot) {
    Write-Error "Target directory must not be the same as the library source directory ($SourceRoot)."
    exit 1
}

$script:ActionCount = 0

# $env:OS is only ever "Windows_NT" on Windows — true on both Windows
# PowerShell 5.1 and pwsh, unlike $IsWindows which doesn't exist in 5.1.
$script:IsWindowsPlatform = ($env:OS -eq "Windows_NT")

function Write-InstallAction([string]$Message) {
    $script:ActionCount++
    Write-Host $Message
}

# Copy-LibraryTree: always overwrites the destination — library-owned files
# are meant to always mirror the source library, same as vendored code.
function Copy-LibraryTree([string]$RelSrc, [string]$RelDst) {
    $src = Join-Path $SourceRoot $RelSrc
    $dst = Join-Path $TargetPath $RelDst

    if (-not (Test-Path -LiteralPath $src)) {
        Write-Error "Expected source path missing: $src"
        exit 1
    }

    $existed = Test-Path -LiteralPath $dst

    if ($DryRun) {
        if ($existed) { Write-InstallAction "would overwrite: $RelDst" }
        else { Write-InstallAction "would create: $RelDst" }
        return
    }

    if ($script:IsWindowsPlatform) {
        # robocopy /MIR mirrors src onto dst (creating dst if needed, purging
        # anything in dst not present in src) via APIs that handle long paths
        # reliably — Remove-Item/Copy-Item -Recurse are not long-path-safe on
        # Windows PowerShell 5.1 and fail on deeply nested trees. Exit codes
        # 0-7 are success; 8+ is failure. robocopy itself is Windows-only, so
        # this branch never runs under pwsh on Linux/macOS (see below).
        $null = robocopy $src $dst /MIR /NFL /NDL /NJH /NJS /NC /NS /NP
        if ($LASTEXITCODE -ge 8) {
            Write-Error "robocopy failed copying $src to $dst (exit code $LASTEXITCODE)"
            exit 1
        }
    }
    else {
        # Non-Windows pwsh (e.g. CI's ubuntu-latest): no robocopy, and no
        # MAX_PATH limitation to work around, so plain Remove-Item +
        # Copy-Item -Recurse mirrors src onto dst just as well.
        if ($existed) {
            Remove-Item -LiteralPath $dst -Recurse -Force
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
    }

    if ($existed) { Write-InstallAction "overwrote: $RelDst" }
    else { Write-InstallAction "created: $RelDst" }
}

$BeginMarker = "<!-- BEGIN context-engineering-protocol SKILLS (auto-generated, do not edit) -->"
$EndMarker = "<!-- END context-engineering-protocol SKILLS -->"

# Merge-AgentsMd: writes/replaces only the marked block in the target's
# AGENTS.md, leaving any other content in that file untouched. Creates the
# file (with just the block) if it doesn't exist yet.
function Merge-AgentsMd {
    $src = Join-Path $SourceRoot "AGENTS.md"
    $dst = Join-Path $TargetPath "AGENTS.md"

    if (-not (Test-Path -LiteralPath $src)) {
        Write-Error "Expected source file missing: $src"
        exit 1
    }

    $dstExists = Test-Path -LiteralPath $dst
    $dstContent = ""
    $hasBlock = $false
    if ($dstExists) {
        $dstContent = Get-Content -LiteralPath $dst -Raw
        $hasBlock = $dstContent.Contains($BeginMarker)
    }

    if ($DryRun) {
        if ($hasBlock) { Write-InstallAction "would update block in: AGENTS.md" }
        elseif ($dstExists) { Write-InstallAction "would append block to: AGENTS.md" }
        else { Write-InstallAction "would create: AGENTS.md" }
        return
    }

    $srcContent = Get-Content -LiteralPath $src -Raw
    $srcContent = $srcContent.TrimEnd("`r", "`n")
    $block = "$BeginMarker`n$srcContent`n$EndMarker"

    if ($hasBlock) {
        $pattern = [regex]::Escape($BeginMarker) + "[\s\S]*?" + [regex]::Escape($EndMarker)
        $evaluator = { param($match) $block }
        $newContent = [regex]::Replace($dstContent, $pattern, $evaluator)
        Set-Content -LiteralPath $dst -Value $newContent -NoNewline
        Write-InstallAction "updated block in: AGENTS.md"
    }
    elseif ($dstExists) {
        $newContent = $dstContent.TrimEnd("`r", "`n") + "`n`n$block`n"
        Set-Content -LiteralPath $dst -Value $newContent -NoNewline
        Write-InstallAction "appended block to: AGENTS.md"
    }
    else {
        Set-Content -LiteralPath $dst -Value "$block`n" -NoNewline
        Write-InstallAction "created: AGENTS.md"
    }
}

# New-ContextConfig: creates context-config.yaml from the template with the
# 5-row mechanical substitution, only if not already present.
function New-ContextConfig {
    $src = Join-Path $SourceRoot "starter_kits/context_engineering/context-config.yaml.template"
    $dst = Join-Path $TargetPath "context-config.yaml"

    if (-not (Test-Path -LiteralPath $src)) {
        Write-Error "Expected source file missing: $src"
        exit 1
    }

    if (Test-Path -LiteralPath $dst) {
        Write-InstallAction "skipped (exists): context-config.yaml"
        return
    }

    if ($DryRun) {
        Write-InstallAction "would create: context-config.yaml"
        return
    }

    $content = Get-Content -LiteralPath $src -Raw
    $content = $content.Replace("<source code root, e.g. app/ or src/>", ".")
    $content = $content.Replace("<requirements docs root, e.g. docs/requirements/>", "docs/requirements/")
    $content = $content.Replace("<external reference root, e.g. specs/external/>", "specs/external/")
    $content = $content.Replace("<org conventions/templates root, e.g. org/>", "org/")
    $content = $content.Replace("<process standards root, e.g. org/process-standards/>", "org/process-standards/")

    Set-Content -LiteralPath $dst -Value $content -NoNewline
    Write-InstallAction "created: context-config.yaml"
}

# New-ProjectGuidelinesPointer: (re)writes
# starter_kit/project_guidelines/.pointer.md. Idempotent and additive —
# creates the drop-zone directory if absent, overwrites only the pointer
# file; any other files placed there are left alone. Only the
# project_guidelines leaf is scaffolded: it's the only one of the 5
# documented starter-kit leaves actually read by a skill shipped in this
# repo (compiling-project-guidelines); the other 4 have no shipped
# library-source content to point at.
function New-ProjectGuidelinesPointer {
    $leafDir = Join-Path $TargetPath "starter_kit/project_guidelines"
    $dst = Join-Path $leafDir ".pointer.md"
    $existed = Test-Path -LiteralPath $dst

    if ($DryRun) {
        if ($existed) { Write-InstallAction "would update: starter_kit/project_guidelines/.pointer.md" }
        else { Write-InstallAction "would create: starter_kit/project_guidelines/.pointer.md" }
        return
    }

    if (-not (Test-Path -LiteralPath $leafDir)) {
        New-Item -ItemType Directory -Path $leafDir -Force | Out-Null
    }

    $pointerContent = @'
# project_guidelines — starter-kit drop-zone

This directory holds project-owned, human-curated material for `project_guidelines`.
Current template and README: `starter_kits/project_guidelines/` in the
skills library this project pulls from.

This file is regenerated by the installer's -InitProject/--init-project mode
and by `/ult-repo-layout init`/`reconcile` — do not edit it directly. Place
your own files alongside it; they are never touched.
'@

    Set-Content -LiteralPath $dst -Value $pointerContent

    if ($existed) { Write-InstallAction "overwrote: starter_kit/project_guidelines/.pointer.md" }
    else { Write-InstallAction "created: starter_kit/project_guidelines/.pointer.md" }
}

Copy-LibraryTree ".github/skills" ".github/skills"
Copy-LibraryTree ".github/prompts" ".github/prompts"
Copy-LibraryTree ".cursor/rules" ".cursor/rules"
Merge-AgentsMd

if ($InitProject) {
    New-ContextConfig
    New-ProjectGuidelinesPointer
}

Write-Host ""
if ($DryRun) {
    Write-Host "Dry run complete ($script:ActionCount action(s) previewed) - no files were written."
}
else {
    Write-Host "Install complete: $script:ActionCount action(s) taken in $TargetPath"
}
