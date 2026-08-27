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

.PARAMETER Only
    Install only the named skill(s) instead of the full set. Comma-separated
    skill directory names, e.g. "compiling-project-guidelines,ult-codegraph".
    Copies just each named skill's .github/skills/<name>/,
    .github/prompts/<name>.prompt.md, and .cursor/rules/<name>.mdc, and trims
    AGENTS.md's merged block down to only those skills' rows.

.PARAMETER Runtime
    Which tool the install targets. .github/skills/ is always copied (every
    value reads it natively via the CEP skill format). What else comes
    along:
      claude   - skills only.
      copilot  - skills + .github/prompts/ (each prompt file is a thin
                 pointer back into .github/skills/).
      cursor   - skills + .github/prompts/ + .cursor/rules/.
      codex    - skills + AGENTS.md merge (codex reads project instructions
                 from AGENTS.md, not a prompts/rules tree).
      both     - everything above, unconditionally (default; unchanged
                 behavior when this parameter is omitted).

.PARAMETER DryRun
    Print what would be done without writing anything.
#>
[CmdletBinding()]
param(
    [string]$TargetPath = "",
    [switch]$InitProject,
    [string]$Only = "",
    [ValidateSet("claude", "copilot", "cursor", "codex", "both")]
    [string]$Runtime = "both",
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

# ValidNames: every skill directory that actually ships in this repo.
$ValidNames = @(Get-ChildItem -LiteralPath (Join-Path $SourceRoot ".github/skills") -Directory |
    ForEach-Object { $_.Name })

# OnlyNames: trimmed, comma-split entries from -Only, validated against
# $ValidNames. Empty when -Only wasn't passed, which every downstream check
# below treats as "install everything".
$OnlyNames = @()
if (-not [string]::IsNullOrWhiteSpace($Only)) {
    $OnlyNames = @($Only -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })

    foreach ($name in $OnlyNames) {
        if ($ValidNames -notcontains $name) {
            Write-Error "Unknown skill in -Only: $name`nAvailable skills: $($ValidNames -join ', ')"
            exit 1
        }
    }
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
    $isDir = (Get-Item -LiteralPath $src).PSIsContainer

    if ($DryRun) {
        if ($existed) { Write-InstallAction "would overwrite: $RelDst" }
        else { Write-InstallAction "would create: $RelDst" }
        return
    }

    if ($script:IsWindowsPlatform -and $isDir) {
        # robocopy /MIR mirrors src onto dst (creating dst if needed, purging
        # anything in dst not present in src) via APIs that handle long paths
        # reliably — Remove-Item/Copy-Item -Recurse are not long-path-safe on
        # Windows PowerShell 5.1 and fail on deeply nested trees. Exit codes
        # 0-7 are success; 8+ is failure. robocopy itself is Windows-only, so
        # this branch never runs under pwsh on Linux/macOS (see below).
        # /XD excludes gitignored local build artifacts (__pycache__,
        # .pytest_cache) that may exist in the source clone's working tree
        # if tests were ever run there — these must never leak into an
        # installed target project. Also excludes tests/ itself: no
        # consumer runs CEP's own unit tests once installed (measured on a
        # full install: 7 tests/ dirs, 51 files, 755K — shipping into
        # every target for no reason any installed skill needs).
        $null = robocopy $src $dst /MIR /XD __pycache__ .pytest_cache tests /NFL /NDL /NJH /NJS /NC /NS /NP
        if ($LASTEXITCODE -ge 8) {
            Write-Error "robocopy failed copying $src to $dst (exit code $LASTEXITCODE)"
            exit 1
        }
    }
    elseif ($script:IsWindowsPlatform) {
        # robocopy /MIR requires directory args on both sides, so a single
        # file (e.g. a -Only run's <name>.prompt.md/.mdc) needs robocopy's
        # dir+dir+filename form instead — still the same long-path-safe API.
        $srcDir = Split-Path -Parent $src
        $dstDir = Split-Path -Parent $dst
        $leaf = Split-Path -Leaf $src
        $null = robocopy $srcDir $dstDir $leaf /NFL /NDL /NJH /NJS /NC /NS /NP
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

        # No robocopy /XD equivalent here, so strip gitignored local build
        # artifacts (__pycache__, .pytest_cache) and tests/ itself
        # post-copy instead — same reasoning as the Windows branch above.
        if ((Get-Item -LiteralPath $dst).PSIsContainer) {
            Get-ChildItem -LiteralPath $dst -Recurse -Force -Directory |
                Where-Object { $_.Name -eq "__pycache__" -or $_.Name -eq ".pytest_cache" -or $_.Name -eq "tests" } |
                Remove-Item -Recurse -Force
        }
    }

    if ($existed) { Write-InstallAction "overwrote: $RelDst" }
    else { Write-InstallAction "created: $RelDst" }
}

$BeginMarker = "<!-- BEGIN context-engineering-protocol SKILLS (auto-generated, do not edit) -->"
$EndMarker = "<!-- END context-engineering-protocol SKILLS -->"

# Format-AgentsMdForOnly: returns Content with ONLY a generated table data row
# dropped — one whose first cell is a recognized skill name ($ValidNames)
# that isn't in $OnlyNames. Every other line — header, separator, the
# trailing "Generated by..." note, blank lines, or anything whose first cell
# isn't a recognized skill name at all — is always kept as-is. This is what
# lets it tell "| Skill | Description | Path |" (header) and "|---|---|---|"
# (separator) apart from real skill rows without hardcoding their text:
# neither "Skill" nor "---" is ever a valid skill dir name. Degrades safely to
# "keep everything" if AGENTS.md's format changes.
function Format-AgentsMdForOnly([string]$Content) {
    $lines = $Content -split "`r`n|`n"
    $kept = foreach ($line in $lines) {
        $cells = $line -split '\|'
        if ($cells.Count -ge 4) {
            $name = $cells[1].Trim()
            if (($ValidNames -contains $name) -and ($OnlyNames -notcontains $name)) {
                continue
            }
        }
        $line
    }
    return ($kept -join "`r`n")
}

# Merge-AgentsMd: writes/replaces only the marked block in the target's
# AGENTS.md, leaving any other content in that file untouched. Creates the
# file (with just the block) if it doesn't exist yet. When $OnlyNames is
# non-empty, the embedded block is trimmed to just those skills' rows via
# Format-AgentsMdForOnly, so the target's AGENTS.md never advertises a skill
# that wasn't actually installed.
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
    if ($OnlyNames.Count -gt 0) {
        $srcContent = Format-AgentsMdForOnly $srcContent
    }
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
    $script:OwnedPaths += "AGENTS.md"
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
# file; any other files placed there are left alone. project_guidelines is
# the only documented starter-kit drop-zone — it's the one actually read by
# a skill shipped in this repo (compiling-project-guidelines).
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

# CepWizardSkillName: the one skill whose install also bundles CEP's own
# project docs alongside it (see Copy-CepWizardDocs below) - named once here
# rather than repeated as a literal at each call site.
$CepWizardSkillName = "ult-cep-wizard"

# Copy-CepWizardDocs: bundles CEP's own project docs (CONCEPT.md, PROTOCOL.md,
# README.md, FAQ.md) into the installed ult-cep-wizard skill's own docs/
# subdirectory, so its in-app docs viewer (wizard_docs.py) has real CEP
# content to serve in every install that includes this skill. Previously
# this script only ever copied .github/skills/, .github/prompts/, and
# .cursor/rules/, so wizard_docs.py's docs viewer had nothing to find in any
# real install regardless of its own root-detection logic — see
# wizard_docs.py's module docstring for the reader side of this fix. Callers
# below only invoke this when the wizard skill itself is actually being
# installed.
#
# Deliberately does NOT bundle case-studies/ - measured on a full install:
# 83 files, 8.6M, the single largest thing this function ever copied, almost
# none of it needed for the wizard's own onboarding flow (the 4 docs above
# cover that). wizard_docs.py's list_docs() already treats a missing
# case-studies/ as "not available" and degrades cleanly - no reader-side
# change needed for this.
function Copy-CepWizardDocs {
    Copy-LibraryTree "CONCEPT.md" ".github/skills/$CepWizardSkillName/docs/CONCEPT.md"
    Copy-LibraryTree "PROTOCOL.md" ".github/skills/$CepWizardSkillName/docs/PROTOCOL.md"
    Copy-LibraryTree "README.md" ".github/skills/$CepWizardSkillName/docs/README.md"
    Copy-LibraryTree "FAQ.md" ".github/skills/$CepWizardSkillName/docs/FAQ.md"
}

# New-CepInstallManifest: writes .cep-install.json at the target root — the
# one place any CEP-shipped script can ask "which paths did the installer
# itself put here", instead of each guessing independently via its own
# hardcoded exclusion list. $OwnedPaths is exactly the set of top-level
# relative paths this run actually wrote, built up by the caller alongside
# each Copy-LibraryTree/New-ProjectGuidelinesPointer call above rather than
# hardcoded here, so the manifest can never drift out of sync with what the
# run actually did. Always overwrites — same "library-owned files always
# mirror the source" rule Copy-LibraryTree follows — so re-running the
# installer keeps the manifest in sync with whatever the run just did.
function New-CepInstallManifest {
    param(
        [string[]]$OwnedPaths,
        [string]$Mode,
        [string[]]$OnlySkills
    )

    if ($DryRun) {
        Write-InstallAction "would write: .cep-install.json"
        return
    }

    $dst = Join-Path $TargetPath ".cep-install.json"
    # .cep-install.json records its own path too - it's a file this run
    # itself wrote, same as everything else in $OwnedPaths, and consumers
    # (discover_layers.py/cep_retrofit.py/scaffold_state.py's manifest
    # readers) should never treat it as project-authored content either.
    $OwnedPaths += ".cep-install.json"
    # RuntimeList: the -Runtime selection expressed as the manifest's own
    # `runtime` array — "both" means literally both tools got their trees
    # copied, so it expands to both names; "claude"/"copilot" alone record
    # just the one value this run actually scoped itself to. This is itself
    # an if/else-expression assignment, so the same single-element-array
    # collapse described below applies here too — the else branch needs its
    # own unary-comma guard, not just the one on $manifest.only_skills.
    $RuntimeList = if ($Runtime -eq "both") { @("claude", "copilot") } else { ,@($Runtime) }
    # ConvertTo-Json gotcha: an `if (...) { $arr } else { $null }` expression
    # captured as a hashtable value silently collapses a *single-element*
    # array to a bare scalar (verified: a 2+-element array is unaffected,
    # and a direct `key = $arr` assignment like owned_paths below is also
    # unaffected — only this if/else-expression shape triggers it). The
    # unary comma operator (,$OnlySkills) forces array-ness through the
    # if-branch regardless of element count, so `--only <one-skill>` still
    # round-trips as a JSON array instead of a bare string. runtime below
    # uses the same direct `key = $arr` assignment shape as owned_paths
    # (not the if/else-expression shape), so it isn't subject to the
    # collapse and needs no comma guard even when -Runtime is "claude" or
    # "copilot" alone (a single-element $RuntimeList).
    $manifest = [ordered]@{
        schema_version = 1
        runtime        = $RuntimeList
        mode           = $Mode
        only_skills    = if ($OnlySkills.Count -gt 0) { ,$OnlySkills } else { $null }
        owned_paths    = $OwnedPaths
        installed_at   = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
    $json = $manifest | ConvertTo-Json -Depth 5
    Set-Content -LiteralPath $dst -Value $json -NoNewline
    Write-InstallAction "wrote: .cep-install.json"
}

# IncludePrompts / IncludeCursorRules / IncludeAgentsMd: .github/skills/ is
# always copied (every -Runtime value reads it natively via the CEP skill
# format); which of the other three trees comes along is scoped per-value
# instead of one switch conflating all of them — see the .PARAMETER Runtime
# doc comment above for the full per-value mapping. "both" is today's
# unconditional copy of everything, unchanged when -Runtime is omitted.
$IncludePrompts = @("copilot", "cursor", "both") -contains $Runtime
$IncludeCursorRules = @("cursor", "both") -contains $Runtime
$IncludeAgentsMd = @("codex", "both") -contains $Runtime

$OwnedPaths = @()
if ($OnlyNames.Count -gt 0) {
    foreach ($name in $OnlyNames) {
        Copy-LibraryTree ".github/skills/$name" ".github/skills/$name"
        $OwnedPaths += ".github/skills/$name"
        if ($IncludePrompts) {
            Copy-LibraryTree ".github/prompts/$name.prompt.md" ".github/prompts/$name.prompt.md"
            $OwnedPaths += ".github/prompts/$name.prompt.md"
        }
        if ($IncludeCursorRules) {
            Copy-LibraryTree ".cursor/rules/$name.mdc" ".cursor/rules/$name.mdc"
            $OwnedPaths += ".cursor/rules/$name.mdc"
        }
        if ($name -eq $CepWizardSkillName) {
            Copy-CepWizardDocs
            $OwnedPaths += ".github/skills/$CepWizardSkillName/docs"
        }
    }
}
else {
    Copy-LibraryTree ".github/skills" ".github/skills"
    $OwnedPaths += ".github/skills"
    if ($IncludePrompts) {
        Copy-LibraryTree ".github/prompts" ".github/prompts"
        $OwnedPaths += ".github/prompts"
    }
    if ($IncludeCursorRules) {
        Copy-LibraryTree ".cursor/rules" ".cursor/rules"
        $OwnedPaths += ".cursor/rules"
    }
    Copy-CepWizardDocs
    $OwnedPaths += ".github/skills/$CepWizardSkillName/docs"
}
if ($IncludeAgentsMd) {
    Merge-AgentsMd
}

if ($InitProject) {
    New-ContextConfig
    New-ProjectGuidelinesPointer
    $OwnedPaths += "context-config.yaml"
    $OwnedPaths += "starter_kit/project_guidelines"
}

$CepInstallMode = if ($OnlyNames.Count -gt 0) { "only" } else { "full" }
New-CepInstallManifest -OwnedPaths $OwnedPaths -Mode $CepInstallMode -OnlySkills $OnlyNames

Write-Host ""
if ($DryRun) {
    Write-Host "Dry run complete ($script:ActionCount action(s) previewed) - no files were written."
}
else {
    Write-Host "Install complete: $script:ActionCount action(s) taken in $TargetPath"
}
