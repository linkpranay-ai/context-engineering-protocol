# Security Policy

## Supported Versions

This project is in `0.x` preview. Security fixes are applied to the latest published version only.

| Version | Supported |
| --- | --- |
| 0.2.x | Yes |
| 0.1.x | No |

## Scope

Most of this repo is static skill/prompt/script content with no runtime attack
surface of its own — it runs inside whatever agent runtime or CI job invokes it, under
that environment's own security posture.

`ult-layout-wizard` (D24) is the one exception, and the first place this repo binds a
real network port. It is a **local, user-launched, on-demand** tool: it starts when
you run it, binds `127.0.0.1` only, and exits when you close it or hit Ctrl+C —
never a background daemon or a hosted/managed service (see `ROADMAP.md`'s "Not on
this roadmap" section). While it's running, it has a real auth model (single-use
bootstrap token, session cookie, CSRF nonce, idle timeout), real Origin/Host
validation, and real path-containment checks — because a bound port is a bound port,
regardless of how short-lived the process is. Full detail:
[`.github/skills/ult-layout-wizard/references/wizard-security-model.md`](.github/skills/ult-layout-wizard/references/wizard-security-model.md).

**Phase 0 is read-only by design** — no mutating HTTP route is registered anywhere in
the current server, so there is no write-path attack surface to report against yet.
A future phase that adds a write endpoint will extend this section additively (the
same auth/CSRF/containment plumbing already exists for exactly that reason), not
replace it — this paragraph is written so that addition doesn't require restructuring
this section, just updating the "no mutating route" claim once one exists.

If you find an issue in `ult-layout-wizard` — a containment bypass, an auth/session
flaw, a CSRF gap, or anything letting a request from outside `127.0.0.1` be treated as
trusted — please report it privately per the process below rather than opening a
public issue.

## Reporting a Vulnerability

Please do not open a public issue for a sensitive security report.

Use GitHub's private vulnerability reporting feature if it is enabled for this repository. If that is not available, contact the maintainer through the GitHub account that owns this repository and include:

- A short description of the issue
- A minimal reproduction or affected file path
- Any impact you believe the issue may have
- Whether the report may be publicly credited after a fix

For non-sensitive bugs, open a regular GitHub issue.
