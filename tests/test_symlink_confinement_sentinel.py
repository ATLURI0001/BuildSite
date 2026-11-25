"""Tests for SymlinkConfinementSentinel."""

import os
import pytest
from pathlib import Path
from buildsite.symlink_confinement_sentinel import (
    ConfinementError,
    PathTraversalViolationError,
    SymlinkConfinementSentinel,
    SymlinkJailbreakError,
    SymlinkRecursionLoopError,
)


@pytest.fixture
def test_sandbox(tmp_path):
    root = tmp_path / "site_root"
    root.mkdir()

    assets = root / "assets"
    assets.mkdir()
    (assets / "style.css").write_text("body { color: black; }")
    (assets / "app.js").write_text("console.log('init');")

    outside = tmp_path / "outside_secrets"
    outside.mkdir()
    (outside / ".env").write_text("SECRET_KEY=leak_me")

    return root, outside


def test_nominal_resolution(test_sandbox):
    root, _ = test_sandbox
    sentinel = SymlinkConfinementSentinel(root)

    resolved = sentinel.resolve_and_verify("assets/style.css")
    assert resolved == (root / "assets" / "style.css").resolve()
    assert resolved.is_file()

    metrics = sentinel.get_metrics()
    assert metrics["total_scanned"] == 1
    assert metrics["jailbreaks_intercepted"] == 0


def test_path_traversal_detection(test_sandbox):
    root, _ = test_sandbox
    sentinel = SymlinkConfinementSentinel(root)

    # Relative path escaping root via ../
    with pytest.raises(PathTraversalViolationError):
        sentinel.resolve_and_verify("../outside_secrets/.env")

    # Null byte injection
    with pytest.raises(PathTraversalViolationError):
        sentinel.resolve_and_verify("assets/style.css\x00.png")

    assert sentinel.get_metrics()["traversal_attempts_blocked"] == 2


def test_symlink_jailbreak_interception(test_sandbox):
    root, outside = test_sandbox
    sentinel = SymlinkConfinementSentinel(root)

    symlink_path = root / "assets" / "leaked_env"
    try:
        os.symlink(outside / ".env", symlink_path)
        with pytest.raises(SymlinkJailbreakError) as exc_info:
            sentinel.resolve_and_verify("assets/leaked_env")
        assert "escapes confined root directory" in str(exc_info.value)
    except (OSError, NotImplementedError):
        # Fallback to simulated symlink resolution for platforms lacking unprivileged symlink privileges (Windows)
        from unittest.mock import patch
        with patch.object(Path, "is_symlink", return_value=True), \
             patch.object(Path, "resolve", return_value=(outside / ".env").resolve()):
            with pytest.raises(SymlinkJailbreakError) as exc_info:
                sentinel.resolve_and_verify("assets/leaked_env")
            assert "escapes confined root directory" in str(exc_info.value)

    assert sentinel.get_metrics()["jailbreaks_intercepted"] == 1


def test_internal_symlinks_permitted(test_sandbox):
    root, _ = test_sandbox
    sentinel = SymlinkConfinementSentinel(root, allow_internal_symlinks=True)

    internal_symlink = root / "assets" / "style_link.css"
    target_file = (root / "assets" / "style.css").resolve()
    try:
        os.symlink(root / "assets" / "style.css", internal_symlink)
        resolved = sentinel.resolve_and_verify("assets/style_link.css")
        assert resolved == target_file
    except (OSError, NotImplementedError):
        from unittest.mock import patch
        with patch.object(Path, "is_symlink", return_value=True), \
             patch.object(Path, "resolve", return_value=target_file):
            resolved = sentinel.resolve_and_verify("assets/style_link.css")
            assert resolved == target_file


def test_disallow_all_symlinks(test_sandbox):
    root, _ = test_sandbox
    sentinel = SymlinkConfinementSentinel(root, allow_internal_symlinks=False)

    internal_symlink = root / "assets" / "style_link.css"
    try:
        os.symlink(root / "assets" / "style.css", internal_symlink)
        with pytest.raises(SymlinkJailbreakError) as exc_info:
            sentinel.resolve_and_verify("assets/style_link.css")
        assert "Symlinks are disallowed by configuration" in str(exc_info.value)
    except (OSError, NotImplementedError):
        from unittest.mock import patch
        with patch.object(Path, "is_symlink", return_value=True):
            with pytest.raises(SymlinkJailbreakError) as exc_info:
                sentinel.resolve_and_verify("assets/style_link.css")
            assert "Symlinks are disallowed by configuration" in str(exc_info.value)


def test_safe_walk(test_sandbox):
    root, _ = test_sandbox
    sentinel = SymlinkConfinementSentinel(root)

    files = sentinel.safe_walk()
    file_names = {f.name for f in files}
    assert "style.css" in file_names
    assert "app.js" in file_names
