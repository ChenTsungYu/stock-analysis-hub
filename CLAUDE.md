# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo does

Automated collection of articles from the MimiVsJames Substack (`mimivsjames2.substack.com`). A daily GitHub Actions workflow logs into Substack, downloads every post as Markdown, and commits the results back to the repo.

## Commands

Dependency management uses `uv` (matches the CI workflow).

```bash
uv sync                                    # install dependencies
uv run playwright install chromium --with-deps   # required once, for Playwright login flow
uv run python mimiVsJamesArticles/fetch_substack.py   # run the scraper
uv run python -m unittest discover -s tests            # run tests
uv run python -m unittest tests.test_fetch_substack     # run a single test module
```

The scraper needs credentials via environment variables — either a pre-obtained session cookie, or an email/password pair it will use to log in with Playwright:

```bash
SUBSTACK_SID=...                              # pre-obtained substack.sid cookie, OR
SUBSTACK_EMAIL=... SUBSTACK_PASSWORD=...      # credentials for automated Playwright login
```

## Architecture

- `mimiVsJamesArticles/fetch_substack.py` — the active scraper, run both locally and in CI.
  1. **Auth**: uses `SUBSTACK_SID` directly if set; otherwise drives a headless Chromium via Playwright (`get_cookie_via_playwright`) to log in with `SUBSTACK_EMAIL`/`SUBSTACK_PASSWORD` and extract the `substack.sid` session cookie. Substack's default "Continue" action sends a magic link, so the login flow explicitly clicks "Sign in with password" first. On login-form timeout, non-secret diagnostics (screenshot + HTML) are saved to `SUBSTACK_DEBUG_DIR` (default `/tmp/substack-debug`) *before* any credentials are typed, so they're safe to upload as a CI artifact for debugging Cloudflare/challenge pages.
  2. **Fetch**: once authenticated, uses `requests` (not Playwright) against Substack's `api/v1/posts` endpoint to paginate all post metadata, then fetches full `body_html` per-post where missing.
  3. **Convert & save**: `HTMLToText` (a stdlib `HTMLParser` subclass) converts each post's HTML body to plain text; each post is written as its own dated Markdown file (`YYYY-MM-DD_Title.md`) into `mimiVsJamesArticles/`, and `mimiVsJamesArticles/README.md` is regenerated as an index table of all posts.
- `mimiVsJamesArticles/fetch_substack_legacy.py` — an older, manual-cookie-only version (no Playwright, no env vars) kept for reference; not used by CI.
- `.github/workflows/mimiVsJamesSubstack.yaml` — runs daily at 02:00 UTC (10am Taiwan time) plus on manual dispatch. Installs deps via `uv sync --locked` + Playwright's Chromium, runs the scraper with secrets injected as env vars, uploads sign-in diagnostics as a workflow artifact on failure, then commits and pushes any new/changed files under `mimiVsJamesArticles/`.
- `tests/test_fetch_substack.py` — loads `fetch_substack.py` directly via `importlib` (not as an installed package) and stubs out the `requests` module so tests can run without network dependencies installed. Currently covers the login-form-selector waiting logic (`wait_for_login_form`).
