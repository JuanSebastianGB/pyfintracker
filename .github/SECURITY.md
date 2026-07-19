# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

`fin` is a personal-finance CLI. Until 1.0, only the latest minor receives
security fixes. Older versions may stop working with newer SQLite or Python and
are not patched.

## Reporting a Vulnerability

**Please do NOT file a public issue.**

Use GitHub's **"Report a vulnerability"** button under the **Security** tab
of [this repository](https://github.com/JuanSebastianGB/pyfintracker/security).
Private vulnerability reporting is enabled — your report goes directly to the
maintainer.

If you cannot use the web form, email the maintainer
(`@JuanSebastianGB` on GitHub → profile page).

### What to include

- A clear description of the vulnerability and its impact
- Steps to reproduce, ideally with a minimal command or posting set
- The version and Python version affected
- Anything you already know about mitigations

### Response target

- Acknowledgement within 7 days
- Triage and a fix or a documented waiver within 30 days for critical issues

### Disclosure timeline

We follow coordinated disclosure: reporters agree to give us reasonable time
to ship a fix before public write-up. We credit reporters in the release
notes unless asked otherwise.

## Scope

In scope:

- Money-handling bugs (silent truncation, wrong decimals, balance-violating
  transactions that get persisted)
- SQL injection or any path that lets a posting or account name reach SQL
- Path traversal or arbitrary file write via CLI args
- Anything that lets a non-root user escape the SQLite sandbox

Out of scope:

- Denial-of-service via malformed posting files in attacker-controlled inputs
- Bugs requiring physical/local access to the user's machine
- Reports against the cloud-side of httpx dependencies (this tool is
  local-first and pulls FX rates via public APIs; report those upstream)
