"""Tests for duplicate resolution (FOUND-02)."""
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PACKAGE_DIR = PROJECT_ROOT / "openarena_perception"


class TestNoDuplicates:
    def test_no_root_duplicates(self):
        """No .py file should exist in both root and package."""
        root_py = {f.name for f in PROJECT_ROOT.glob("*.py")}
        pkg_py = {f.name for f in PACKAGE_DIR.glob("*.py")}
        duplicates = root_py & pkg_py
        # __init__.py is expected at package level only
        duplicates.discard("__init__.py")
        assert duplicates == set(), f"Duplicate files in root and package: {duplicates}"

    def test_entry_points_exist(self):
        """Core entry-point scripts must exist in root."""
        for script in ["play.py", "item_tour.py", "map_explorer.py"]:
            assert (PROJECT_ROOT / script).is_file(), f"Missing entry point: {script}"


class TestGitignore:
    def test_gitignore_has_env(self):
        gitignore = PROJECT_ROOT / ".gitignore"
        assert gitignore.is_file(), ".gitignore missing"
        content = gitignore.read_text()
        assert ".env" in content, ".gitignore must include .env"

    def test_gitignore_has_pycache(self):
        gitignore = PROJECT_ROOT / ".gitignore"
        content = gitignore.read_text()
        assert "__pycache__" in content
