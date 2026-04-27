# Security Policy

## Threat Model

This package is designed for **trusted local AI agents** running on the user's own
machine. The `delegate_shell` MCP tool deliberately has **no allowlist** - the
agent can run any shell command the calling user has permission to run.

This is the explicit design goal: closing autonomy gaps in tier-restricted
environments (Claude Code Cowork, where shells are click-only). It is not
appropriate for:

- Public-facing MCP servers
- Multi-tenant deployments
- Any context where the calling agent isn't fully trusted

## Tested Attack Vectors

The 0.1.0 release was tested against the following vectors. Test scripts live in
`tests/security/`. All tests passed (no exploitable behaviour found).

| Vector                       | Result | Mitigation |
|------------------------------|--------|------------|
| Shell-metachar injection     | SAFE   | argv list-based subprocess (no shell parsing) |
| Path traversal in cwd        | SAFE   | subprocess.run validates cwd, raises OSError on bad path (caught, returns exit_code=-3) |
| Path traversal in target_path | SAFE  | os.path.abspath + os.path.isdir checks before subprocess invocation |
| Symbolic link follow         | SAFE*  | *graphify CLI honors symlinks; trust the target_path argument |
| ReDoS via classifier regex   | SAFE   | All patterns bounded (no nested quantifiers); pathological inputs tested up to 10MB |
| OOM via stdin                | SAFE   | 1MB stdin cap (truncated with warning) |
| OOM via stdout/stderr        | SAFE   | 256KB stdout / 64KB stderr caps |
| Audit log unbounded growth   | NOTE   | No automatic rotation - rotate via cron / scheduled task; see Hardening section |
| Race on concurrent calls     | SAFE   | Each call gets fresh subprocess; no shared mutable state |
| Env var injection            | SAFE   | env dict merged into copy of os.environ; no shell substitution |

## Hardening Recommendations

If you want to gate `delegate_shell` more strictly than the default, three patterns:

### 1. Allowlist wrapper

```python
ALLOWED = {"git", "pip", "python", "graphify", "npm", "node", "gh"}

def safe_delegate(argv, **kw):
    if argv[0] not in ALLOWED:
        return {"ok": False, "stderr": f"command {argv[0]!r} not allowed"}
    from autotrigger.delegate import delegate_shell_dict
    return delegate_shell_dict(argv, **kw)
```

### 2. Env-var gating

```bash
# Disable shell delegation entirely (the MCP tool will return an error)
set CHHARBOT_DELEGATE_DISABLED=1
```

### 3. Audit log rotation

Add to your scheduled tasks / cron:

```powershell
# Rotate when audit log exceeds 10 MB (Windows scheduled task)
$log = "$env:USERPROFILE\.chharbot\delegate-audit.log"
if ((Get-Item $log).Length -gt 10MB) {
    Move-Item $log "$log.$(Get-Date -Format yyyyMMdd)"
}
```

## Reporting

For security issues, please open a private security advisory on the repository
rather than a public issue. Maintainers will respond within 7 days.
