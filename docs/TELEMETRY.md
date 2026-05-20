# BGI Telemetry

> **Off by default.** Set `BGI_TELEMETRY=1` to opt in. This page is the
> full record of what we collect, why, and how to disable it.

## TL;DR

- **What:** A single anonymous ping when `bgi mcp` starts.
- **When:** Only if you've explicitly set `BGI_TELEMETRY=1` in your
  environment. Otherwise nothing is sent, ever.
- **Why:** Without this, we have no way to tell whether anyone is using
  BGI. The validation evidence shows it works on the test repos —
  telemetry tells us if it works for real users.

## What we collect

If, and only if, `BGI_TELEMETRY=1` is set:

| Field | Example | Purpose |
|---|---|---|
| `event_kind` | `mcp_start` | Distinguishes startup pings from future tool-call events |
| `version` | `0.1.4` | Track which BGI versions are actually in use |
| `os` | `linux` / `darwin` / `windows` / `other` | Coarse platform mix |
| `os_version` | `5.15.0` | Kernel/release string (no machine name) |
| `repo_id` | `a1b2c3d4e5f6` | Stable 12-char hash, see below |
| `repo_size_bucket` | `S` / `M` / `L` / `XL` | Bucketed file count |
| `tool_name` | `cluster_of_file` | _(future)_ Which MCP tool was invoked |

That's the entire schema. No fields are added without a corresponding
update to this document.

## What we never collect

- File paths, source code, or any identifiers from your repo
- Your repo name, organization name, or remote URL
- Your username, email, or any personal information
- Server-side IP addresses (the BGI website does not log them)
- Query strings, prompt text, or AI assistant outputs

## How `repo_id` works

`repo_id` is computed locally as the first 12 hex characters of:

```
sha256(`git remote get-url origin` output)
```

If your repo has no remote configured, BGI falls back to hashing the
absolute path of your checkout. Either way, the value is deterministic
(same repo → same id) but not reversible: knowing `a1b2c3d4e5f6` tells
us nothing about which repo it came from.

This lets us answer "is this the same repo we saw last week?" without
ever knowing which repo it is.

## How to enable telemetry

```bash
export BGI_TELEMETRY=1
bgi mcp --graph bgi-graph.json --fuse-graph fuse-graph.json
```

## How to disable telemetry

Telemetry is off by default. If you previously enabled it:

```bash
unset BGI_TELEMETRY
# or
export BGI_TELEMETRY=0
```

Either disables it for the current shell. Your shell's startup files
(`~/.bashrc`, `~/.zshrc`, etc.) are the only place a persistent setting
could live — BGI does not write to user config.

## Network behavior

- Endpoint: `https://bigindexer.com/api/telemetry`
- 2-second hard timeout
- Failures are silent — if the network is down, BGI keeps working
- Sent on a daemon thread; never blocks the user's workflow

## Where the data goes

The telemetry endpoint is a simple Node service running on
`bigindexer.com`. It validates the JSON schema (any unknown field is
rejected outright) and appends accepted entries to a JSONL file on the
server. The server is not accessible to third parties.

The internal weekly rollup lives at
`output/rollups/weekly.md` and aggregates this data alongside public
GitHub traffic numbers. Aggregate counts may be quoted publicly when
relevant; individual events are not published.

## Source

- Client: [`bgi/telemetry.py`](../bgi/bgi/telemetry.py)
- Server endpoint: [`website/server.js`](../website/server.js) (search for
  `/api/telemetry`)
- Tests: [`tests/test_telemetry.py`](../tests/test_telemetry.py)

If anything in this document is wrong or unclear, or if you'd like a
field removed, [open an issue](https://github.com/ahmedxuhri/bigindexer/issues).
