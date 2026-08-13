#!/usr/bin/env python3
"""
MimiVsJames Substack 文章爬取腳本
支援兩種模式：
  1. 直接填入 SUBSTACK_SID cookie（手動）
  2. 填入帳密，自動用 Playwright 登入取得 cookie（自動化）
"""

import requests
import json
import re
import os
import sys
import time
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path

# ==============================
# 設定（優先讀取環境變數）
# ==============================
SUBSTACK_SID      = os.environ.get("SUBSTACK_SID", "")
SUBSTACK_EMAIL    = os.environ.get("SUBSTACK_EMAIL", "")
SUBSTACK_PASSWORD = os.environ.get("SUBSTACK_PASSWORD", "")

PUBLICATION = "mimivsjames2"
BASE_URL    = f"https://{PUBLICATION}.substack.com"
OUTPUT_DIR  = os.path.dirname(os.path.abspath(__file__))

SIGN_IN_URL = "https://substack.com/sign-in"
EMAIL_SELECTOR = 'input[type="email"], input[name="email"]'
PASSWORD_SELECTOR = 'input[type="password"], input[name="password"]'
PASSWORD_LOGIN_SELECTOR = 'a:has-text("Sign in with password")'
LOGIN_TIMEOUT_MS = 60_000
# GitHub-hosted runners are more likely to be served a slow Cloudflare
# JavaScript challenge when Playwright's default HeadlessChrome UA is used.
CHROME_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ── HTML → 純文字 ──────────────────────────────────────────
class HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_tags = {"script", "style", "head"}
        self.current_skip = False
        self.block_tags = {"p","div","h1","h2","h3","h4","h5","h6",
                           "li","tr","br","hr","blockquote"}

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags: self.current_skip = True
        if tag in self.block_tags: self.result.append("\n")
        if tag == "img":
            alt = dict(attrs).get("alt", "")
            if alt: self.result.append(f"[圖片：{alt}]")

    def handle_endtag(self, tag):
        if tag in self.skip_tags: self.current_skip = False
        if tag in self.block_tags: self.result.append("\n")

    def handle_data(self, data):
        if not self.current_skip: self.result.append(data)

    def get_text(self):
        text = "".join(self.result)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

def html_to_text(html):
    p = HTMLToText(); p.feed(html or ""); return p.get_text()


# ── Playwright 登入取 cookie ───────────────────────────────
def wait_for_login_form(page, timeout=LOGIN_TIMEOUT_MS):
    """Wait for either of Substack's supported email input variants."""
    email_input = page.locator(EMAIL_SELECTOR).first
    email_input.wait_for(state="visible", timeout=timeout)
    return email_input


def save_login_diagnostics(page):
    """Save non-secret diagnostics before credentials are entered."""
    debug_dir = Path(os.environ.get("SUBSTACK_DEBUG_DIR", "/tmp/substack-debug"))
    debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(debug_dir / "sign-in-timeout.png"), full_page=True)
        (debug_dir / "sign-in-timeout.html").write_text(page.content(), encoding="utf-8")
        print(f"ℹ️ 登入頁診斷檔已寫入 {debug_dir}")
    except Exception as exc:
        print(f"ℹ️ 無法儲存登入頁診斷檔：{type(exc).__name__}")


def wait_for_session_cookie(ctx, timeout=LOGIN_TIMEOUT_MS):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        sid = next((c["value"] for c in ctx.cookies() if c["name"] == "substack.sid"), None)
        if sid:
            return sid
        time.sleep(1)
    raise RuntimeError("登入逾時：找不到 substack.sid cookie（可能需要互動式驗證）")


def get_cookie_via_playwright(email, password):
    from playwright.sync_api import sync_playwright
    print("🔐 使用 Playwright 登入 Substack...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=CHROME_USER_AGENT, locale="en-US")
            page = ctx.new_page()
            page.goto(SIGN_IN_URL, wait_until="domcontentloaded", timeout=LOGIN_TIMEOUT_MS)
            try:
                email_input = wait_for_login_form(page)
            except Exception:
                # This happens before typing any credentials, so the artifact is safe
                # to upload from CI for diagnosing Cloudflare/challenge pages.
                save_login_diagnostics(page)
                raise

            # Substack's default Continue action sends a magic link.  Explicitly
            # select the password route before submitting the credentials.
            password_login = page.locator(PASSWORD_LOGIN_SELECTOR).first
            if password_login.is_visible(timeout=5_000):
                password_login.click()
                email_input = wait_for_login_form(page)
            page.locator(PASSWORD_SELECTOR).first.wait_for(state="visible", timeout=LOGIN_TIMEOUT_MS)
            email_input.fill(email)
            page.locator(PASSWORD_SELECTOR).first.fill(password)
            page.locator('form button[type="submit"]').first.click()
            sid = wait_for_session_cookie(ctx)
        finally:
            browser.close()
    print("✅ 登入成功，取得 session cookie")
    return sid


# ── Substack API ───────────────────────────────────────────
def make_session(sid):
    s = requests.Session()
    s.cookies.set("substack.sid", sid, domain=f"{PUBLICATION}.substack.com")
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": BASE_URL})
    return s

def fetch_all_posts(session):
    posts, offset = [], 0
    while True:
        r = session.get(f"{BASE_URL}/api/v1/posts", params={"limit": 50, "offset": offset})
        r.raise_for_status()
        batch = r.json()
        if not batch: break
        posts.extend(batch)
        print(f"  已取得 {len(posts)} 篇 metadata...")
        if len(batch) < 50: break
        offset += 50
    return posts

def fetch_post_detail(session, slug):
    r = session.get(f"{BASE_URL}/api/v1/posts/{slug}")
    r.raise_for_status()
    return r.json()

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def save_post(post, output_dir):
    title    = post.get("title", "untitled")
    slug     = post.get("slug", "")
    date_str = post.get("post_date", "")[:10]
    subtitle = post.get("subtitle", "") or ""
    url      = post.get("canonical_url", f"{BASE_URL}/p/{slug}")
    audience = post.get("audience", "")
    body_html = post.get("body_html") or ""
    body_text = html_to_text(body_html) if body_html else post.get("truncated_body_text", "")

    lines  = [f"# {title}", ""]
    lines += [f"**日期：** {date_str}", f"**作者：** MimiVsJames", f"**連結：** {url}"]
    if subtitle: lines += [f"**副標：** {subtitle}"]
    if audience: lines += [f"**類型：** {audience}"]
    lines += ["", "---", ""]
    lines.append(body_text if body_text else "（本篇內容主要為圖片，請至原始連結查看）")

    filename = f"{date_str}_{sanitize_filename(title[:50])}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath


# ── 主程式 ────────────────────────────────────────────────
def main():
    # 取得 session cookie
    sid = SUBSTACK_SID
    if not sid:
        if SUBSTACK_EMAIL and SUBSTACK_PASSWORD:
            sid = get_cookie_via_playwright(SUBSTACK_EMAIL, SUBSTACK_PASSWORD)
        else:
            print("❌ 請設定 SUBSTACK_SID 或 SUBSTACK_EMAIL + SUBSTACK_PASSWORD")
            sys.exit(1)

    session = make_session(sid)
    print(f"📡 連接 {BASE_URL}...")
    all_posts = fetch_all_posts(session)
    print(f"\n✅ 共 {len(all_posts)} 篇，開始下載內文...\n")

    saved, failed = [], []
    for i, post in enumerate(all_posts, 1):
        slug  = post.get("slug", "")
        title = post.get("title", slug)
        print(f"  [{i}/{len(all_posts)}] {title[:60]}...")
        try:
            if not post.get("body_html"):
                detail = fetch_post_detail(session, slug)
                post.update(detail)
            fp = save_post(post, OUTPUT_DIR)
            saved.append(fp)
            print(f"    ✓ {os.path.basename(fp)}")
        except Exception as e:
            print(f"    ✗ 失敗：{e}")
            failed.append(slug)

    # 更新索引
    rows = "\n".join(
        f"| {p.get('post_date','')[:10]} | {p.get('title','')} |"
        for p in all_posts
    )
    index = f"""# MimiVsJames 美股即時策略分享 - 文章索引

> 來源：{BASE_URL}
> 更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 共 {len(saved)} 篇

---

| 日期 | 標題 |
|------|------|
{rows}
"""
    with open(os.path.join(OUTPUT_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(index)

    print(f"\n🎉 完成！成功 {len(saved)} 篇，失敗 {len(failed)} 篇")
    if failed: print(f"   失敗：{failed}")

if __name__ == "__main__":
    main()
