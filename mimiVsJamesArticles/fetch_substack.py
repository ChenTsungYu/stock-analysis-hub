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
from html.parser import HTMLParser
from datetime import datetime

# ==============================
# 設定（優先讀取環境變數）
# ==============================
SUBSTACK_SID      = os.environ.get("SUBSTACK_SID", "")
SUBSTACK_EMAIL    = os.environ.get("SUBSTACK_EMAIL", "")
SUBSTACK_PASSWORD = os.environ.get("SUBSTACK_PASSWORD", "")

PUBLICATION = "mimivsjames2"
BASE_URL    = f"https://{PUBLICATION}.substack.com"
OUTPUT_DIR  = os.path.dirname(os.path.abspath(__file__))


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
def get_cookie_via_playwright(email, password):
    from playwright.sync_api import sync_playwright
    print("🔐 使用 Playwright 登入 Substack...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://substack.com/sign-in")
        page.wait_for_selector('input[type="email"]', timeout=15000)
        page.fill('input[type="email"]', email)
        page.click('button[type="submit"]')
        page.wait_for_selector('input[type="password"]', timeout=10000)
        page.fill('input[type="password"]', password)
        page.click('button[type="submit"]')
        # 等待登入完成
        page.wait_for_url("https://substack.com/**", timeout=20000)
        page.wait_for_timeout(2000)
        cookies = ctx.cookies()
        browser.close()
    sid = next((c["value"] for c in cookies if c["name"] == "substack.sid"), None)
    if not sid:
        raise RuntimeError("登入失敗：找不到 substack.sid cookie")
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