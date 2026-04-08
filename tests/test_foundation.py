"""Tests for Phase 1 foundation: folder structure, pyproject.toml."""
from pathlib import Path
import pytest

PACKAGE_DIR = Path(__file__).parent.parent / "openarena_perception"
PROJECT_ROOT = Path(__file__).parent.parent

BRAIN_DIRS = [
    "perception", "combat", "navigation", "memory", "tactics",
    "strategy", "reflexes", "brainstem", "skills", "api",
]


class TestFolderStructure:
    @pytest.mark.parametrize("dirname", BRAIN_DIRS)
    def test_brain_directory_exists(self, dirname):
        d = PACKAGE_DIR / dirname
        assert d.is_dir(), f"Missing directory: openarena_perception/{dirname}/"

    @pytest.mark.parametrize("dirname", BRAIN_DIRS)
    def test_brain_directory_has_init(self, dirname):
        init = PACKAGE_DIR / dirname / "__init__.py"
        assert init.is_file(), f"Missing: openarena_perception/{dirname}/__init__.py"

    def test_pyproject_exists(self):
        assert (PROJECT_ROOT / "pyproject.toml").is_file()

    def test_bot_toml_exists(self):
        assert (PROJECT_ROOT / "bot.toml").is_file()
