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


class _Response:
    def __init__(self, posts):
        self.posts = posts

    def raise_for_status(self):
        pass

    def json(self):
        return self.posts


class _Session:
    def __init__(self, posts):
        self.posts = posts
        self.requests = []

    def get(self, url, params):
        self.requests.append((url, params))
        return _Response(self.posts)


class WaitForLoginFormTests(unittest.TestCase):
    def test_waits_for_both_substack_email_selector_variants_for_ci_timeout(self):
        page = _Page()

        result = fetch_substack.wait_for_login_form(page, timeout=60_000)

        self.assertIs(result, page.email_input)
        self.assertEqual(page.selectors, [fetch_substack.EMAIL_SELECTOR])
        self.assertEqual(page.email_input.calls, [{"state": "visible", "timeout": 60_000}])


class FetchPostsTests(unittest.TestCase):
    def test_requests_and_returns_only_the_latest_five_posts(self):
        session = _Session([{"slug": str(index)} for index in range(10)])

        posts = fetch_substack.fetch_all_posts(session)

        self.assertEqual(len(posts), 5)
        self.assertEqual(session.requests[0][1], {"limit": 5, "offset": 0})


class HtmlImageTests(unittest.TestCase):
    def test_embeds_downloaded_images_at_their_original_html_position(self):
        body = "<p>before</p><img src='one.jpg' alt='chart'><p>after</p>"

        text = fetch_substack.html_to_text(body, ["![chart](images/post/01.jpg)"])

        self.assertIn("before\n\n![chart](images/post/01.jpg)\n\nafter", text)

    def test_extracts_absolute_and_relative_image_urls_in_order(self):
        images = fetch_substack.extract_image_sources(
            "<img src='/first.png'><img data-src='https://cdn.example/second.webp'>"
        )

        self.assertEqual(
            images,
            [
                ("https://mimivsjames2.substack.com/first.png", ""),
                ("https://cdn.example/second.webp", ""),
            ],
        )


if __name__ == "__main__":
    unittest.main()
