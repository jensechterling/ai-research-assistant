"""Tests for scripts/run.sh: the weekly backup runs even after a stopped pipeline run."""
import shutil
import subprocess

import pytest

from src.config import get_project_dir


def _setup(tmp_path, pipeline_exit: int, backup_exit: int = 0):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(get_project_dir() / "scripts" / "run.sh", scripts)
    backup = scripts / "backup_feeds.sh"
    backup.write_text(f"#!/bin/bash\ntouch \"$(dirname \"$0\")/../backup-ran\"\nexit {backup_exit}\n")
    backup.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(f"#!/bin/bash\nexit {pipeline_exit}\n")
    uv.chmod(0o755)
    return subprocess.run(["bash", str(scripts / "run.sh")], capture_output=True, text=True,
                          env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)})


@pytest.mark.parametrize("pipeline_exit", [0, 1])
def test_backup_runs_and_pipeline_status_is_kept(tmp_path, pipeline_exit):
    result = _setup(tmp_path, pipeline_exit)

    assert (tmp_path / "backup-ran").exists()
    assert result.returncode == pipeline_exit


def test_backup_failure_fails_an_otherwise_successful_run(tmp_path):
    result = _setup(tmp_path, pipeline_exit=0, backup_exit=3)

    assert result.returncode == 3
