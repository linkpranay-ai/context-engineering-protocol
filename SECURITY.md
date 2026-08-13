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

`ult-cep-wizard` (D24) is the one exception, and the first place this repo binds a
real network port. It is a **local, user-launched, on-demand** tool: it starts when
you run it, binds `127.0.0.1` only, and exits when you close it or hit Ctrl+C —
never a background daemon or a hosted/managed service (see `ROADMAP.md`'s "Not on
this roadmap" section). While it's running, it has a real auth model (single-use
bootstrap token, session cookie, CSRF nonce, idle timeout), real Origin/Host
validation, and real path-containment checks — because a bound port is a bound port,
regardless of how short-lived the process is.

**The server has a real write path.** `POST /api/stage`, `POST /api/apply`, and
`POST /api/discover` are registered, mutating routes — staging a layout decision,
committing it, and re-running discovery, respectively. Every one of them sits behind
the same three gates, in order, before the handler runs: Origin/Host validation
(`_origin_host_ok()`), a valid session cookie (`_require_session()`), and a CSRF
token in a request header (`check_csrf()`, header-only — never read from a cookie or
query string). Neither `/api/stage` nor `/api/apply` writes to disk directly; both
hand off to `ult-repo-layout`'s own `confirm_layers.py` module (imported and called
in-process — the same code path its CLI uses) to do the actual commit. Full detail,
including the exact gate order and each route's own additional guards:
[`.github/skills/ult-cep-wizard/references/wizard-security-model.md`](.github/skills/ult-cep-wizard/references/wizard-security-model.md).

If you find an issue in `ult-cep-wizard` — a containment bypass, an auth/session
flaw, a CSRF gap, a way to reach `/api/stage`, `/api/apply`, or `/api/discover`
without clearing all three gates, or anything letting a request from outside
`127.0.0.1` be treated as trusted — please report it privately per the process below
rather than opening a public issue.

## Reporting a Vulnerability

Please do not open a public issue for a sensitive security report.

Use GitHub's private vulnerability reporting feature if it is enabled for this repository. If that is not available, contact the maintainer through the GitHub account that owns this repository and include:

- A short description of the issue
- A minimal reproduction or affected file path
- Any impact you believe the issue may have
- Whether the report may be publicly credited after a fix

For non-sensitive bugs, open a regular GitHub issue.
