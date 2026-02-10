## Context

The pipeline runs as a scheduled job (launchd on macOS, cron on Linux) and can also be triggered manually via `ai-research-assistant run`. There is no mechanism to prevent overlapping runs. When two instances run simultaneously, they both query the same SQLite database for pending entries, leading to duplicate processing and wasted Claude API calls. SQLite's default locking prevents corruption but doesn't prevent logical conflicts.

## Goals / Non-Goals

**Goals:**
- Prevent concurrent pipeline runs with a simple, reliable lock mechanism
- Exit cleanly with a clear message when another run is in progress
- Handle stale locks from crashed processes
- Zero new dependencies

**Non-Goals:**
- Distributed locking (single-machine only)
- Lock contention metrics or monitoring
- Automatic stale lock recovery (manual `--force` is sufficient)

## Decisions

### D1: `fcntl.flock()` file lock over PID file

**Choice:** Use `fcntl.flock()` on `data/pipeline.lock` for advisory locking.

**Why not PID file?** PID files are fragile — if the process crashes, the PID file stays and requires stale detection logic (check if PID is alive, handle PID reuse). `fcntl.flock()` is automatically released by the OS when the process exits, crashes, or is killed. No stale lock problem under normal circumstances.

**Why not `filelock` library?** It's a dependency for a single use. `fcntl` is in the standard library and sufficient for single-machine use. Note: `fcntl` is Unix-only, but the pipeline already targets macOS/Linux.

### D2: Lock acquired in `run_pipeline()`, not in CLI

**Choice:** The `run_pipeline()` function acquires the lock, not the Click command.

**Rationale:** The lock protects the pipeline logic, not the CLI entry point. This keeps `--dry-run` lock-free (dry runs don't write to the database) and makes the lock testable without invoking CLI.

### D3: `--force` flag writes PID for diagnostics

**Choice:** When `--force` is used to override a lock, log a warning. The lock file stores the PID of the holding process for diagnostic messages ("Pipeline already running, PID 12345").

**Rationale:** Users need to know which process to investigate when the lock blocks them. PID in the lock file is purely informational (not used for stale detection — that's `flock`'s job).

## Risks / Trade-offs

- **`fcntl` is Unix-only** → Acceptable — the pipeline targets macOS and Linux. Windows users would need an alternative (`msvcrt.locking`), but we already show "manual setup" for Windows scheduling. If Windows support is added later, the lock can be swapped.
- **Stale lock on NFS** → `flock` doesn't work reliably on NFS. Not a concern — `data/` is always local.
- **`--force` can cause conflicts** → By design — it's an escape hatch, not a default. Warning is logged.
