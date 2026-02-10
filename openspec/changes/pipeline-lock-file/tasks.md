## 1. Pipeline lock implementation

- [x] 1.1 Add `PipelineLock` class to `src/pipeline.py` using `fcntl.flock()` on `data/pipeline.lock`, writing PID to lock file
- [x] 1.2 Wrap `run_pipeline()` processing logic with lock acquire/release (skip lock for `--dry-run`)
- [x] 1.3 Add `--force` flag to `run` CLI command in `src/main.py`, pass through to `run_pipeline()`

## 2. Tests

- [x] 2.1 Test that lock is acquired and PID is written to lock file
- [x] 2.2 Test that second invocation is blocked when lock is held
- [x] 2.3 Test that `--dry-run` does not acquire lock
- [x] 2.4 Test that `--force` bypasses lock with warning

## 3. Documentation

- [x] 3.1 Add `data/pipeline.lock` to `.gitignore`
- [x] 3.2 Update CHANGELOG with pipeline lock entry
