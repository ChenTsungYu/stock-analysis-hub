#!/usr/bin/env python3
"""
MimiVsJames Substack 文章爬取腳本
使用方式：
1. 在 Chrome 開啟 mimivsjames2.substack.com 並登入
2. 按 F12 → Application → Cookies → substack.sid
3. 複製 substack.sid 的值填入下方 COOKIE
4. 執行：python3 fetch_substack.py
"""

import requests
import json
import re
import os
from html.parser import HTMLParser
from datetime import datetime

# ==============================
# 填入你的 substack.sid cookie
# ==============================
SUBSTACK_SID = ""
# ==============================

PUBLICATION = "mimivsjames2"
BASE_URL = f"https://{PUBLICATION}.substack.com"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


class HTMLToText(HTMLParser):
    """簡易 HTML 轉純文字"""
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_tags = {"script", "style", "head"}
        self.current_skip = False
        self.block_tags = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                           "li", "tr", "br", "hr", "blockquote"}

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.current_skip = True
        if tag in self.block_tags:
            self.result.append("\n")
        if tag == "a":
            for name, val in attrs:
                if name == "href" and val:
                    self.result.append(f"[")
        if tag == "img":
            alt = dict(attrs).get("alt", "")
            if alt:
                self.result.append(f"[圖片：{alt}]")

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.current_skip = False
        if tag == "a":
            self.result.append("]")
        if tag in self.block_tags:
            self.result.append("\n")

    def handle_data(self, data):
        if not self.current_skip:
            self.result.append(data)

    def get_text(self):
        text = "".join(self.result)
        # 清理多餘空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html):
    parser = HTMLToText()
    parser.feed(html or "")
    return parser.get_text()


def fetch_all_posts(session, offset=0, limit=50):
    """取得文章列表（僅 metadata，無內文）"""
    url = f"{BASE_URL}/api/v1/posts"
    params = {"limit": limit, "offset": offset}
    r = session.get(url, params=params)
    r.raise_for_status()
    return r.json()


def fetch_post_detail(session, slug):
    """取得單篇文章完整內容"""
    url = f"{BASE_URL}/api/v1/posts/{slug}"
    r = session.get(url)
    r.raise_for_status()
    return r.json()


def sanitize_filename(name):
    """移除檔名不合法字元"""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def save_post(post, output_dir):
    """將文章儲存為 Markdown 檔案"""
    title = post.get("title", "untitled")
    slug = post.get("slug", "")
    date_str = post.get("post_date", "")[:10]  # YYYY-MM-DD
    subtitle = post.get("subtitle", "") or ""
    url = post.get("canonical_url", f"{BASE_URL}/p/{slug}")
    audience = post.get("audience", "")

    # 取得內文（優先用 body_html，fallback 到 truncated_body_text）
    body_html = post.get("body_html") or ""
    body_text = html_to_text(body_html) if body_html else post.get("truncated_body_text", "")

    # 組合 Markdown
    lines = [f"# {title}", ""]
    lines += [f"**日期：** {date_str}"]
    lines += [f"**作者：** MimiVsJames"]
    lines += [f"**連結：** {url}"]
    if subtitle:
        lines += [f"**副標：** {subtitle}"]
    if audience:
        lines += [f"**類型：** {audience}"]
    lines += ["", "---", ""]

    if body_text:
        lines.append(body_text)
    else:
        lines.append("（本篇內容主要為圖片，請至原始連結查看）")

    content = "\n".join(lines)

    filename = f"{date_str}_{sanitize_filename(title[:50])}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def main():
    if SUBSTACK_SID == "在這裡填入你的 substack.sid cookie 值":
        print("❌ 請先填入 substack.sid cookie！")
        return

    session = requests.Session()
    session.cookies.set("substack.sid", SUBSTACK_SID, domain=f"{PUBLICATION}.substack.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL,
    })

    print(f"📡 連接 {BASE_URL}...")

    # 取得所有文章列表
    all_posts = []
    offset = 0
    while True:
        batch = fetch_all_posts(session, offset=offset)
        if not batch:
            break
        all_posts.extend(batch)
        print(f"  已取得 {len(all_posts)} 篇文章 metadata...")
        if len(batch) < 50:
            break
        offset += 50

    print(f"\n✅ 共找到 {len(all_posts)} 篇文章，開始下載內容...\n")

    saved = []
    failed = []

    for i, post in enumerate(all_posts, 1):
        slug = post.get("slug", "")
        title = post.get("title", slug)
        print(f"  [{i}/{len(all_posts)}] {title[:60]}...")

        try:
            # 如果 body_html 已在列表 API 中（通常不會），直接用
            if not post.get("body_html"):
                detail = fetch_post_detail(session, slug)
                post.update(detail)

            filepath = save_post(post, OUTPUT_DIR)
            saved.append(filepath)
            print(f"    ✓ 儲存：{os.path.basename(filepath)}")

        except Exception as e:
            print(f"    ✗ 失敗：{e}")
            failed.append(slug)

    # 建立索引
    index_lines = [
        f"# MimiVsJames 美股即時策略分享 - 文章索引",
        "",
        f"> 來源：{BASE_URL}",
        f"> 爬取日期：{datetime.now().strftime('%Y-%m-%d')}",
        f"> 共 {len(saved)} 篇文章",
        "",
        "---",
        "",
        "| 日期 | 標題 |",
        "|------|------|",
    ]
    for post in all_posts:
        date = post.get("post_date", "")[:10]
        title = post.get("title", "")
        slug = post.get("slug", "")
        index_lines.append(f"| {date} | {title} |")

    with open(os.path.join(OUTPUT_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))

    print(f"\n🎉 完成！成功 {len(saved)} 篇，失敗 {len(failed)} 篇")
    if failed:
        print(f"   失敗的 slug：{failed}")


if __name__ == "__main__":
    main()
