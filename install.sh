#!/usr/bin/env bash
# Installs this repo's skill library (.github/skills/, .github/prompts/,
# .cursor/rules/, AGENTS.md) into an existing target project directory.
#
# Not a package-manager-style installer: no version pinning, no network
# fetch. Run this from inside a clone of context-engineering-oss, pointed at
# a separate target project directory.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh --target <dir> [--init-project] [--dry-run] [--only <skill1,skill2>] [--runtime claude|copilot|cursor|codex|both]

  --target <dir>    Required. Path to an existing target project directory.
  --init-project    Also scaffold context-config.yaml (if absent) and
                     starter_kit/project_guidelines/.pointer.md (if absent).
  --only <names>    Install only the named skill(s) instead of the full set.
                     Comma-separated skill directory names, e.g.
                     "compiling-project-guidelines,ult-codegraph". Copies just
                     each named skill's .github/skills/<name>/,
                     .github/prompts/<name>.prompt.md, and
                     .cursor/rules/<name>.mdc, and trims AGENTS.md's merged
                     block down to only those skills' rows.
  --runtime <v>     Which tool the install targets. .github/skills/ is
                     always copied (every value reads it natively via
                     the CEP skill format). What else comes along:
                       claude   - skills only.
                       copilot  - skills + .github/prompts/ (each prompt
                                  file is a thin pointer back into
                                  .github/skills/).
                       cursor   - skills + .github/prompts/ + .cursor/rules/.
                       codex    - skills + AGENTS.md merge (codex reads
                                  project instructions from AGENTS.md,
                                  not a prompts/rules tree).
                       both     - everything above, unconditionally
                                  (default; unchanged behavior when this
                                  flag is omitted).
  --dry-run         Print what would be done without writing anything.
  -h, --help        Show this help.
EOF
}

TARGET=""
INIT_PROJECT=0
DRY_RUN=0
ONLY=""
RUNTIME="both"

while [ $# -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --init-project)
      INIT_PROJECT=1
      shift
      ;;
    --only)
      ONLY="${2:-}"
      shift 2
      ;;
    --runtime)
      RUNTIME="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "Error: --target <dir> is required." >&2
  usage >&2
  exit 1
fi

case "$RUNTIME" in
  claude|copilot|cursor|codex|both) ;;
  *)
    echo "Error: --runtime must be one of: claude, copilot, cursor, codex, both (got: $RUNTIME)" >&2
    exit 1
    ;;
esac

if [ ! -d "$TARGET" ]; then
  echo "Error: target directory does not exist: $TARGET" >&2
  exit 1
fi

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TARGET="$(cd "$TARGET" && pwd)"

if [ "$SOURCE_ROOT" = "$TARGET" ]; then
  echo "Error: target directory must not be the same as the library source directory ($SOURCE_ROOT)." >&2
  exit 1
fi

# ONLY_NAMES: trimmed, comma-split entries from --only, validated against the
# actual skill directories that ship in this repo. Empty when --only wasn't
# passed, which every downstream check below treats as "install everything".
ONLY_NAMES=()
if [ -n "$ONLY" ]; then
  IFS=',' read -ra _only_raw <<< "$ONLY"
  for _name in "${_only_raw[@]}"; do
    _name="$(echo "$_name" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$_name" ] && ONLY_NAMES+=("$_name")
  done

  VALID_NAMES=()
  for _dir in "$SOURCE_ROOT"/.github/skills/*/; do
    VALID_NAMES+=("$(basename "$_dir")")
  done

  for _name in "${ONLY_NAMES[@]}"; do
    _found=0
    for _valid in "${VALID_NAMES[@]}"; do
      [ "$_name" = "$_valid" ] && _found=1 && break
    done
    if [ "$_found" -eq 0 ]; then
      printf 'Error: unknown skill in --only: %s\n' "$_name" >&2
      printf 'Available skills: %s\n' "$(IFS=', '; echo "${VALID_NAMES[*]}")" >&2
      exit 1
    fi
  done
fi

ACTION_COUNT=0

log_action() {
  ACTION_COUNT=$((ACTION_COUNT + 1))
  echo "$1"
}

# copy_tree <src-rel-path> <dst-rel-path>
# Always overwrites the destination — library-owned files are meant to
# always mirror the source library, same as vendored code.
copy_tree() {
  local src="$SOURCE_ROOT/$1"
  local dst="$TARGET/$2"

  if [ ! -e "$src" ]; then
    echo "Error: expected source path missing: $src" >&2
    exit 1
  fi

  local existed=0
  [ -e "$dst" ] && existed=1

  if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$existed" -eq 1 ]; then
      log_action "would overwrite: $2"
    else
      log_action "would create: $2"
    fi
    return
  fi

  mkdir -p "$(dirname "$dst")"
  rm -rf "$dst"
  cp -R "$src" "$dst"

  # Strip gitignored local build artifacts (__pycache__, .pytest_cache) that
  # may exist in the source clone's working tree if tests were ever run
  # there — these must never leak into an installed target project. Also
  # strip tests/ itself: no consumer runs CEP's own unit tests once
  # installed (measured on a full install: 7 tests/ dirs, 51 files, 755K —
  # shipping into every target for no reason any installed skill needs).
  if [ -d "$dst" ]; then
    find "$dst" -depth -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name 'tests' \) -exec rm -rf {} +
  fi

  if [ "$existed" -eq 1 ]; then
    log_action "overwrote: $2"
  else
    log_action "created: $2"
  fi
}

BEGIN_MARKER="<!-- BEGIN context-engineering-protocol SKILLS (auto-generated, do not edit) -->"
END_MARKER="<!-- END context-engineering-protocol SKILLS -->"

# filter_agents_md_for_only <src-file>: prints src-file's content, dropping
# ONLY a generated table data row whose first cell is a recognized skill name
# (one of VALID_NAMES) that isn't in ONLY_NAMES. Every other line — header,
# separator, the trailing "Generated by..." note, blank lines, or anything
# whose first cell isn't a recognized skill name at all — is always kept
# as-is. This is what lets it tell "| Skill | Description | Path |" (header)
# and "|---|---|---|" (separator) apart from real skill rows without
# hardcoding their text: neither "Skill" nor "---" is ever a valid skill dir
# name. Degrades safely to "keep everything" if AGENTS.md's format changes.
filter_agents_md_for_only() {
  awk -F'|' -v only="$(IFS=,; echo "${ONLY_NAMES[*]}")" \
           -v valid="$(IFS=,; echo "${VALID_NAMES[*]}")" '
    BEGIN {
      n = split(only, oarr, ",")
      for (i = 1; i <= n; i++) is_selected[oarr[i]] = 1
      n = split(valid, varr, ",")
      for (i = 1; i <= n; i++) is_valid[varr[i]] = 1
    }
    {
      if (NF >= 3) {
        name = $2
        gsub(/^[ \t]+|[ \t]+$/, "", name)
        if ((name in is_valid) && !(name in is_selected)) next
      }
      print
    }
  ' "$1"
}

# merge_agents_md: writes/replaces only the marked block in the target's
# AGENTS.md, leaving any other content in that file untouched. Creates the
# file (with just the block) if it doesn't exist yet. When ONLY_NAMES is
# non-empty, the embedded block is trimmed to just those skills' rows via
# filter_agents_md_for_only, so the target's AGENTS.md never advertises a
# skill that wasn't actually installed.
merge_agents_md() {
  local src="$SOURCE_ROOT/AGENTS.md"
  local dst="$TARGET/AGENTS.md"

  if [ ! -f "$src" ]; then
    echo "Error: expected source file missing: $src" >&2
    exit 1
  fi

  local dst_exists=0
  [ -f "$dst" ] && dst_exists=1

  local has_block=0
  if [ "$dst_exists" -eq 1 ] && grep -qF "$BEGIN_MARKER" "$dst"; then
    has_block=1
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$has_block" -eq 1 ]; then
      log_action "would update block in: AGENTS.md"
    elif [ "$dst_exists" -eq 1 ]; then
      log_action "would append block to: AGENTS.md"
    else
      log_action "would create: AGENTS.md"
    fi
    return
  fi

  local block_file
  block_file="$(mktemp)"
  {
    printf '%s\n' "$BEGIN_MARKER"
    if [ "${#ONLY_NAMES[@]}" -gt 0 ]; then
      filter_agents_md_for_only "$src"
    else
      cat "$src"
    fi
    printf '%s\n' "$END_MARKER"
  } > "$block_file"

  if [ "$has_block" -eq 1 ]; then
    local before after tmp
    before="$(mktemp)"
    after="$(mktemp)"
    tmp="$(mktemp)"
    awk -v b="$BEGIN_MARKER" 'index($0,b)==1{exit} {print}' "$dst" > "$before"
    awk -v e="$END_MARKER" 'f{print} index($0,e)==1{f=1}' "$dst" > "$after"
    cat "$before" "$block_file" "$after" > "$tmp"
    mv "$tmp" "$dst"
    rm -f "$before" "$after"
    log_action "updated block in: AGENTS.md"
  elif [ "$dst_exists" -eq 1 ]; then
    { cat "$dst"; printf '\n'; cat "$block_file"; } > "${dst}.new"
    mv "${dst}.new" "$dst"
    log_action "appended block to: AGENTS.md"
  else
    cp "$block_file" "$dst"
    log_action "created: AGENTS.md"
  fi
  # AGENTS.md is a merge target, not a file this installer owns outright: it
  # only ever writes its own marked block into it, and everything outside
  # that block is adopter-authored content this run must not claim. So it is
  # recorded in MERGED_PATHS rather than OWNED_PATHS - a consumer that
  # excludes owned_paths wholesale would otherwise silently drop the
  # adopter's own content living in the rest of the file.
  MERGED_PATHS+=("AGENTS.md")

  rm -f "$block_file"
}

# scaffold_context_config: creates context-config.yaml from the template
# with the 5-row mechanical substitution, only if not already present.
scaffold_context_config() {
  local src="$SOURCE_ROOT/starter_kits/context_engineering/context-config.yaml.template"
  local dst="$TARGET/context-config.yaml"

  if [ ! -f "$src" ]; then
    echo "Error: expected source file missing: $src" >&2
    exit 1
  fi

  if [ -f "$dst" ]; then
    log_action "skipped (exists): context-config.yaml"
    return
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    log_action "would create: context-config.yaml"
    return
  fi

  # sed (not bash parameter substitution via command substitution) so the
  # template's exact trailing-newline byte layout survives untouched — the
  # test suite compares this output byte-for-byte against the template
  # read directly in Python.
  sed \
    -e 's#<source code root, e.g. app/ or src/>#.#g' \
    -e 's#<requirements docs root, e.g. docs/requirements/>#docs/requirements/#g' \
    -e 's#<external reference root, e.g. specs/external/>#specs/external/#g' \
    -e 's#<org conventions/templates root, e.g. org/>#org/#g' \
    -e 's#<process standards root, e.g. org/process-standards/>#org/process-standards/#g' \
    "$src" > "$dst"
  log_action "created: context-config.yaml"
  # Recorded as owned only on this branch - the run that actually created
  # the file. An existing context-config.yaml is adopter-authored (the
  # "skipped (exists)" early return above), so a later run must not start
  # claiming it.
  OWNED_PATHS+=("context-config.yaml")
}

# scaffold_pointer: (re)writes starter_kit/project_guidelines/.pointer.md.
# Idempotent and additive — creates the drop-zone directory if absent,
# overwrites only the pointer file; any other files placed there are left
# alone. project_guidelines is the only documented starter-kit drop-zone —
# it's the one actually read by a skill shipped in this repo
# (compiling-project-guidelines).
scaffold_pointer() {
  local leaf_dir="$TARGET/starter_kit/project_guidelines"
  local dst="$leaf_dir/.pointer.md"
  local existed=0
  [ -f "$dst" ] && existed=1

  if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$existed" -eq 1 ]; then
      log_action "would update: starter_kit/project_guidelines/.pointer.md"
    else
      log_action "would create: starter_kit/project_guidelines/.pointer.md"
    fi
    return
  fi

  mkdir -p "$leaf_dir"
  cat > "$dst" <<'POINTER_EOF'
# project_guidelines — starter-kit drop-zone

This directory holds project-owned, human-curated material for `project_guidelines`.
Current template and README: `starter_kits/project_guidelines/` in the
skills library this project pulls from.

This file is regenerated by the installer's -InitProject/--init-project mode
and by `/ult-repo-layout init`/`reconcile` — do not edit it directly. Place
your own files alongside it; they are never touched.
POINTER_EOF

  if [ "$existed" -eq 1 ]; then
    log_action "overwrote: starter_kit/project_guidelines/.pointer.md"
  else
    log_action "created: starter_kit/project_guidelines/.pointer.md"
  fi
  # The pointer file, not the directory around it: project_guidelines is an
  # additive drop-zone whose other files are adopter-owned, and this
  # function only ever writes .pointer.md.
  OWNED_PATHS+=("starter_kit/project_guidelines/.pointer.md")
}

# CEP_WIZARD_SKILL_NAME: the one skill whose install also bundles CEP's own
# project docs alongside it (see copy_cep_wizard_docs below) - named once
# here rather than repeated as a literal at each call site.
CEP_WIZARD_SKILL_NAME="ult-cep-wizard"

# copy_cep_wizard_docs: bundles CEP's own project docs (CONCEPT.md,
# PROTOCOL.md, README.md, FAQ.md) into the installed ult-cep-wizard skill's
# own docs/ subdirectory, so its in-app docs viewer (wizard_docs.py) has
# real CEP content to serve in every install that includes this skill.
# Previously this script only ever copied .github/skills/, .github/prompts/,
# and .cursor/rules/, so wizard_docs.py's docs viewer had nothing to find in
# any real install regardless of its own root-detection logic - see
# wizard_docs.py's module docstring for the reader side of this fix.
# Callers below only invoke this when the wizard skill itself is actually
# being installed.
#
# Deliberately does NOT bundle case-studies/ - measured on a full install:
# 83 files, 8.6M, the single largest thing this function ever copied,
# almost none of it needed for the wizard's own onboarding flow (the 4 docs
# above cover that). wizard_docs.py's list_docs() already treats a missing
# case-studies/ as "not available" and degrades cleanly - no reader-side
# change needed for this.
copy_cep_wizard_docs() {
  copy_tree "CONCEPT.md" ".github/skills/$CEP_WIZARD_SKILL_NAME/docs/CONCEPT.md"
  copy_tree "PROTOCOL.md" ".github/skills/$CEP_WIZARD_SKILL_NAME/docs/PROTOCOL.md"
  copy_tree "README.md" ".github/skills/$CEP_WIZARD_SKILL_NAME/docs/README.md"
  copy_tree "FAQ.md" ".github/skills/$CEP_WIZARD_SKILL_NAME/docs/FAQ.md"
}

OWNED_PATHS=()
# MERGED_PATHS: paths this run wrote *into* without owning them outright -
# today only AGENTS.md, where merge_agents_md writes a marked block and
# leaves the rest of the file to the adopter. Kept separate from
# OWNED_PATHS so a consumer that excludes owned_paths wholesale still sees
# the write recorded without treating the whole file as CEP-generated.
MERGED_PATHS=()

# write_cep_install_manifest <mode>: writes .cep-install.json at the target
# root - the one place any CEP-shipped script can ask "which paths did the
# installer itself put here", instead of each guessing independently via its
# own hardcoded exclusion list. OWNED_PATHS is exactly the set of top-level
# relative paths this run actually wrote, built up alongside each
# copy_tree/scaffold_pointer call below rather than hardcoded here, so the
# manifest can never drift out of sync with what the run actually did.
# Always overwrites - same "library-owned files always mirror the source"
# rule copy_tree follows - so re-running the installer keeps the manifest in
# sync with whatever the run just did.
write_cep_install_manifest() {
  local mode="$1"
  local dst="$TARGET/.cep-install.json"

  if [ "$DRY_RUN" -eq 1 ]; then
    log_action "would write: .cep-install.json"
    return
  fi

  # .cep-install.json records its own path too - it's a file this run
  # itself wrote, same as everything else in OWNED_PATHS, and consumers
  # (discover_layers.py/cep_retrofit.py/scaffold_state.py's manifest
  # readers) should never treat it as project-authored content either.
  local owned_json merged_json only_json runtime_json
  owned_json="$(printf '"%s",' "${OWNED_PATHS[@]}" ".cep-install.json")"
  owned_json="[${owned_json%,}]"
  # merged_paths is always present, and is an empty array on any run that
  # never merged AGENTS.md (e.g. --runtime claude or --runtime copilot), so
  # readers can index it unconditionally. Guarded on the count because an
  # empty array expansion is an error under `set -u` on older bash builds.
  if [ "${#MERGED_PATHS[@]}" -gt 0 ]; then
    merged_json="$(printf '"%s",' "${MERGED_PATHS[@]}")"
    merged_json="[${merged_json%,}]"
  else
    merged_json="[]"
  fi
  if [ "${#ONLY_NAMES[@]}" -gt 0 ]; then
    only_json="$(printf '"%s",' "${ONLY_NAMES[@]}")"
    only_json="[${only_json%,}]"
  else
    only_json="null"
  fi
  # runtime_json: derived from the same include_* flags that gated the real
  # copy/merge work above, so the manifest records the tools this run
  # actually installed for instead of restating the --runtime string. Every
  # value copies .github/skills/, so "claude" is always present; the other
  # three names ride along with the tree each one needs.
  local runtime_names
  runtime_names=("claude")
  if [ "$include_prompts" -eq 1 ]; then
    runtime_names+=("copilot")
  fi
  if [ "$include_cursor_rules" -eq 1 ]; then
    runtime_names+=("cursor")
  fi
  if [ "$include_agents_md" -eq 1 ]; then
    runtime_names+=("codex")
  fi
  runtime_json="$(printf '"%s", ' "${runtime_names[@]}")"
  runtime_json="[${runtime_json%, }]"

  cat > "$dst" <<EOF
{
  "schema_version": 1,
  "runtime": $runtime_json,
  "mode": "$mode",
  "only_skills": $only_json,
  "owned_paths": $owned_json,
  "merged_paths": $merged_json,
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
  log_action "wrote: .cep-install.json"
}

# include_prompts / include_cursor_rules / include_agents_md: .github/skills/
# is always copied (every --runtime value reads it natively via the CEP
# skill format); which of the other three trees comes along is scoped
# per-value instead of one flag conflating all of them - see usage()'s
# --runtime entry for the full per-value mapping. "both" is today's
# unconditional copy of everything, unchanged when --runtime is omitted.
include_prompts=0
include_cursor_rules=0
include_agents_md=0
case "$RUNTIME" in
  claude)
    ;;
  copilot)
    include_prompts=1
    ;;
  cursor)
    include_prompts=1
    include_cursor_rules=1
    ;;
  codex)
    include_agents_md=1
    ;;
  both)
    include_prompts=1
    include_cursor_rules=1
    include_agents_md=1
    ;;
esac

if [ "${#ONLY_NAMES[@]}" -gt 0 ]; then
  for _name in "${ONLY_NAMES[@]}"; do
    copy_tree ".github/skills/$_name" ".github/skills/$_name"
    OWNED_PATHS+=(".github/skills/$_name")
    if [ "$include_prompts" -eq 1 ]; then
      copy_tree ".github/prompts/${_name}.prompt.md" ".github/prompts/${_name}.prompt.md"
      OWNED_PATHS+=(".github/prompts/${_name}.prompt.md")
    fi
    if [ "$include_cursor_rules" -eq 1 ]; then
      copy_tree ".cursor/rules/${_name}.mdc" ".cursor/rules/${_name}.mdc"
      OWNED_PATHS+=(".cursor/rules/${_name}.mdc")
    fi
    if [ "$_name" = "$CEP_WIZARD_SKILL_NAME" ]; then
      copy_cep_wizard_docs
      OWNED_PATHS+=(".github/skills/$CEP_WIZARD_SKILL_NAME/docs")
    fi
  done
else
  copy_tree ".github/skills" ".github/skills"
  OWNED_PATHS+=(".github/skills")
  if [ "$include_prompts" -eq 1 ]; then
    copy_tree ".github/prompts" ".github/prompts"
    OWNED_PATHS+=(".github/prompts")
  fi
  if [ "$include_cursor_rules" -eq 1 ]; then
    copy_tree ".cursor/rules" ".cursor/rules"
    OWNED_PATHS+=(".cursor/rules")
  fi
  copy_cep_wizard_docs
  OWNED_PATHS+=(".github/skills/$CEP_WIZARD_SKILL_NAME/docs")
fi
if [ "$include_agents_md" -eq 1 ]; then
  merge_agents_md
fi

if [ "$INIT_PROJECT" -eq 1 ]; then
  scaffold_context_config
  scaffold_pointer
fi

if [ "${#ONLY_NAMES[@]}" -gt 0 ]; then
  write_cep_install_manifest "only"
else
  write_cep_install_manifest "full"
fi

echo ""
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run complete ($ACTION_COUNT action(s) previewed) — no files were written."
else
  echo "Install complete: $ACTION_COUNT action(s) taken in $TARGET"
fi
