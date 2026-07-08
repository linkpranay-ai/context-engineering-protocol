#!/usr/bin/env python3
"""content_hash.py - content-hash helper for context packages (D19 v2, C1/C2).

Computes the 8-hex-char `content_hash` for a `contexts/<package-id>.yaml`
file. A `<package-id>@<hash8>` tag embeds this value at tagging time;
`CONSUMING-CONTEXT-PACKAGE.md` item 0 compares a tag's `<hash8>` against the
package's *current* `content_hash` field (a plain field read - no
recomputation) to detect drift. Recomputation via this script is only needed
on the write path, whenever `contexts/<package-id>.yaml` is created or
rewritten (ult-context-generate Step 3/Step 10, or a consumer's
domain-enrichment write-back).

Python 3 stdlib only (hashlib, re, sys, pathlib) - vendorable alongside
md_index.py.

CLI:
    python content_hash.py <path-to-yaml>
"""

import hashlib
import re
import sys
from pathlib import Path

# Matches the top-level `content_hash: ...` field (any indentation) so the
# field is excluded from its own input - re-hashing a file that already
# carries a `content_hash` value reproduces that same value, as long as
# nothing else in the file changed.
_CONTENT_HASH_LINE_RE = re.compile(r"^[ \t]*content_hash:.*\n?", re.MULTILINE)


def content_hash8(path):
    """Return the 8-hex-char content hash for the file at `path`.

    Strips the top-level `content_hash:` line (if present), normalizes all
    line endings to `\\n`, and returns the first 8 hex chars of
    sha256(utf-8 bytes).
    """
    text = Path(path).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTENT_HASH_LINE_RE.sub("", text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: content_hash.py <path-to-yaml>", file=sys.stderr)
        return 2
    print(content_hash8(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
