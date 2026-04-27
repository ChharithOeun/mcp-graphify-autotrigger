"""Tests for the cleanup module."""
import os
import tempfile
from pathlib import Path

from autotrigger.cleanup import (
    cleanup_files,
    cleanup_screenshots,
    close_stale_windows,
    run_full_cleanup,
    run_if_milestone,
    SESSION_FILE_PATTERNS,
    MILESTONE_KEYWORDS,
)


def test_cleanup_files_archive(tmp_path):
    # Create some session-pattern files
    (tmp_path / "AB_TEST.ps1").write_text("# test")
    (tmp_path / "AAR_DUMP.log").write_text("log data")
    (tmp_path / "permanent.txt").write_text("KEEP")  # not a pattern

    r = cleanup_files(str(tmp_path), archive=True)
    assert len(r.archived) == 2
    assert (tmp_path / "permanent.txt").exists()
    assert r.archive_dir is not None
    assert Path(r.archive_dir).exists()


def test_cleanup_files_dry_run(tmp_path):
    (tmp_path / "AB_TEST.ps1").write_text("# test")
    r = cleanup_files(str(tmp_path), archive=True, dry_run=True)
    assert r.dry_run is True
    assert len(r.archived) == 1
    # File should NOT actually be moved in dry run
    assert (tmp_path / "AB_TEST.ps1").exists()


def test_run_if_milestone_matches():
    # Returns dict when keyword present
    out = run_if_milestone("we are wrapping up the session end now",
                            workspace=str(Path.cwd()), dry_run=True)
    assert out is not None
    assert "files" in out


def test_run_if_milestone_no_match():
    out = run_if_milestone("just a normal question", workspace=str(Path.cwd()))
    assert out is None


def test_close_stale_windows_dry_run():
    # Dry run shouldn't kill anything
    r = close_stale_windows(dry_run=True)
    # On non-Windows, errors will note Windows-only; that's OK
    assert isinstance(r.closed_windows, list)


def test_milestone_keywords_lowercase():
    for kw in MILESTONE_KEYWORDS:
        assert kw == kw.lower()
