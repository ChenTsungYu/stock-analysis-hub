import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "mimiVsJamesArticles" / "fetch_substack.py"
sys.modules.setdefault("requests", types.ModuleType("requests"))
SPEC = importlib.util.spec_from_file_location("fetch_substack_environment", MODULE_PATH)
fetch_substack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_substack)


class LocalEnvironmentTests(unittest.TestCase):
    def test_loads_root_dotenv_for_local_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv_path = Path(directory) / ".env"
            dotenv_path.write_text("SUBSTACK_EMAIL=local@example.test\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertTrue(fetch_substack.load_local_environment(dotenv_path))
                self.assertEqual(os.environ["SUBSTACK_EMAIL"], "local@example.test")

    def test_ci_does_not_load_dotenv_or_override_github_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv_path = Path(directory) / ".env"
            dotenv_path.write_text("SUBSTACK_EMAIL=local@example.test\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"GITHUB_ACTIONS": "true", "SUBSTACK_EMAIL": "secret@example.test"},
                clear=True,
            ):
                self.assertFalse(fetch_substack.load_local_environment(dotenv_path))
                self.assertEqual(os.environ["SUBSTACK_EMAIL"], "secret@example.test")
