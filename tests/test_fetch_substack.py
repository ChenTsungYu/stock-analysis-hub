import importlib.util
from pathlib import Path
import sys
import types
import unittest


MODULE_PATH = Path(__file__).parents[1] / "mimiVsJamesArticles" / "fetch_substack.py"
SPEC = importlib.util.spec_from_file_location("fetch_substack", MODULE_PATH)
fetch_substack = importlib.util.module_from_spec(SPEC)
# The selector helper has no HTTP dependency; keep this regression test runnable
# with the standard library, as in a fresh checkout before workflow setup.
sys.modules.setdefault("requests", types.ModuleType("requests"))
SPEC.loader.exec_module(fetch_substack)


class _EmailInput:
    def __init__(self):
        self.calls = []

    def wait_for(self, **kwargs):
        self.calls.append(kwargs)


class _Locator:
    def __init__(self, email_input):
        self.first = email_input


class _Page:
    def __init__(self):
        self.email_input = _EmailInput()
        self.selectors = []

    def locator(self, selector):
        self.selectors.append(selector)
        return _Locator(self.email_input)


class WaitForLoginFormTests(unittest.TestCase):
    def test_waits_for_both_substack_email_selector_variants_for_ci_timeout(self):
        page = _Page()

        result = fetch_substack.wait_for_login_form(page, timeout=60_000)

        self.assertIs(result, page.email_input)
        self.assertEqual(page.selectors, [fetch_substack.EMAIL_SELECTOR])
        self.assertEqual(page.email_input.calls, [{"state": "visible", "timeout": 60_000}])


if __name__ == "__main__":
    unittest.main()
