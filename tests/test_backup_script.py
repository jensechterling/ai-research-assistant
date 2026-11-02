"""Tests for the weekly OPML backup in scripts/backup_feeds.sh.

The backup commits only exports/feeds.opml onto the backup/feeds branch and pushes that
branch. The checked-out branch, its index and the working tree are never touched.
"""
import shutil
import subprocess

from src.config import get_project_dir

BRANCH = "backup/feeds"
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _git(repo, *args) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                         env={"PATH": "/usr/bin:/bin", "HOME": str(repo.parent), **IDENTITY})
    return out.stdout.strip()


def _repo(tmp_path, branch: str = "feat/x"):
    """A checkout on `branch` with a bare `origin` and a uv stub that writes feeds.opml from $FEEDS."""
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(get_project_dir() / "scripts" / "backup_feeds.sh", repo / "scripts")
    _git(repo, "init", "-q", "-b", branch)
    (repo / "README.md").write_text("readme\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(remote))
    uv = tmp_path / "uv-stub"
    # Stands in for `uv run ai-research-assistant feeds export --output PATH`
    uv.write_text('#!/bin/bash\nout=exports/feeds.opml\nwhile [ $# -gt 0 ]; do [ "$1" = --output ] && out="$2"; shift; done\n'
                  'mkdir -p "$(dirname "$out")"\nprintf "%s" "$FEEDS" > "$out"\n')
    uv.chmod(0o755)
    return repo, remote, uv


def _run(repo, uv, day: str = "1", feeds: str = "<opml>a</opml>") -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(repo.parent), "DAY_OF_WEEK": day, "UV": str(uv),
           "FEEDS": feeds, **IDENTITY}
    return subprocess.run(["bash", str(repo / "scripts" / "backup_feeds.sh")], capture_output=True, text=True,
                          env=env)


def _remote_commits(remote) -> int:
    return int(_git(remote, "rev-list", "--count", BRANCH))


def test_other_weekday_does_nothing(tmp_path):
    repo, remote, uv = _repo(tmp_path)

    result = _run(repo, uv, day="3")

    assert result.returncode == 0
    assert result.stdout == ""
    assert not (repo / "exports").exists()
    assert _git(remote, "branch", "--list", BRANCH) == ""


def test_first_monday_creates_and_pushes_backup_branch_with_only_the_opml(tmp_path):
    repo, remote, uv = _repo(tmp_path)

    result = _run(repo, uv)

    assert result.returncode == 0, result.stderr
    assert _git(remote, "ls-tree", "-r", "--name-only", BRANCH) == "exports/feeds.opml"
    assert _git(remote, "show", f"{BRANCH}:exports/feeds.opml") == "<opml>a</opml>"
    assert _remote_commits(remote) == 1


def test_checked_out_branch_index_and_staged_changes_are_untouched(tmp_path):
    repo, remote, uv = _repo(tmp_path)
    (repo / "staged.txt").write_text("work in progress\n")
    _git(repo, "add", "staged.txt")
    head_before = _git(repo, "rev-parse", "HEAD")

    result = _run(repo, uv)

    assert result.returncode == 0, result.stderr
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "feat/x"
    assert _git(repo, "rev-parse", "HEAD") == head_before
    assert _git(repo, "diff", "--cached", "--name-only") == "staged.txt"
    assert _git(remote, "branch", "--list", "feat/x") == ""


def test_unchanged_export_makes_no_commit_and_no_push(tmp_path):
    repo, remote, uv = _repo(tmp_path)
    _run(repo, uv)
    tip = _git(remote, "rev-parse", BRANCH)

    result = _run(repo, uv)

    assert result.returncode == 0, result.stderr
    assert "unchanged" in result.stdout
    assert _git(remote, "rev-parse", BRANCH) == tip


def test_changed_export_adds_a_commit_on_top(tmp_path):
    repo, remote, uv = _repo(tmp_path)
    _run(repo, uv)

    result = _run(repo, uv, feeds="<opml>b</opml>")

    assert result.returncode == 0, result.stderr
    assert _remote_commits(remote) == 2
    assert _git(remote, "show", f"{BRANCH}:exports/feeds.opml") == "<opml>b</opml>"


def test_master_checkout_is_not_committed_to(tmp_path):
    repo, remote, uv = _repo(tmp_path, branch="master")
    head_before = _git(repo, "rev-parse", "HEAD")

    result = _run(repo, uv)

    assert result.returncode == 0, result.stderr
    assert _git(repo, "rev-parse", "HEAD") == head_before
    assert _git(remote, "branch", "--list", "master") == ""


def test_checkout_stays_clean_when_the_opml_is_tracked(tmp_path):
    repo, remote, uv = _repo(tmp_path)
    (repo / "exports").mkdir()
    (repo / "exports" / "feeds.opml").write_text("<opml>old</opml>")
    _git(repo, "add", "exports/feeds.opml")
    _git(repo, "commit", "-q", "-m", "track opml")

    result = _run(repo, uv, feeds="<opml>new</opml>")

    assert result.returncode == 0, result.stderr
    assert _git(repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert (repo / "exports" / "feeds.opml").read_text() == "<opml>old</opml>"
    assert _git(remote, "show", f"{BRANCH}:exports/feeds.opml") == "<opml>new</opml>"


def test_failed_push_is_retried_the_next_week_even_when_unchanged(tmp_path):
    repo, remote, uv = _repo(tmp_path)
    _git(repo, "remote", "set-url", "origin", str(tmp_path / "offline.git"))
    first = _run(repo, uv)
    _git(repo, "remote", "set-url", "origin", str(remote))

    second = _run(repo, uv)

    assert first.returncode != 0
    assert second.returncode == 0, second.stderr
    assert _git(remote, "show", f"{BRANCH}:exports/feeds.opml") == "<opml>a</opml>"


def test_backup_continues_from_a_remote_that_is_ahead(tmp_path):
    repo, remote, uv = _repo(tmp_path)
    _run(repo, uv, feeds="<opml>a</opml>")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True, capture_output=True)
    (other / "scripts").mkdir()
    shutil.copy2(get_project_dir() / "scripts" / "backup_feeds.sh", other / "scripts")
    assert _run(other, uv, feeds="<opml>b</opml>").returncode == 0  # a second machine backs up first

    result = _run(repo, uv, feeds="<opml>c</opml>")

    assert result.returncode == 0, result.stderr
    assert _remote_commits(remote) == 3
    assert _git(remote, "show", f"{BRANCH}:exports/feeds.opml") == "<opml>c</opml>"
