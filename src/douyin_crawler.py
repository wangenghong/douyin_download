# -*- coding: utf-8 -*-
"""Douyin web image crawler entry module."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .crawler.models import (
    IMAGE_MODE,
    VIDEO_MODE,
    extract_user_profile,
    is_image_post,
    is_video_post,
    sanitize_filename,
)
from .crawler.browser import create_context, ensure_browser_installed, collect_all_posts
from .crawler.downloader import cache_video_posts, download_image_posts

sys.stdout.reconfigure(encoding="utf-8")


class DouyinCrawler:
    def __init__(
        self,
        user_id,
        cookie_str="",
        max_posts=50,
        output_dir="./output",
        headless=True,
        user_name="",
        crawl_mode=IMAGE_MODE,
    ):
        self.user_id = user_id
        self.cookie_str = cookie_str.strip()
        self.max_posts = max_posts
        self.headless = headless
        self.user_name = user_name.strip() or user_id
        self.crawl_mode = crawl_mode if crawl_mode in {IMAGE_MODE, VIDEO_MODE} else IMAGE_MODE
        self.output_dir = Path(output_dir) / sanitize_filename(self.user_name, max_len=40)
        self.posts = []
        self.selected_posts = []
        self.user_profile = {"user_name": self.user_name, "avatar_url": ""}

    async def run(self):
        await ensure_browser_installed()
        print(f"[+] Target: {self.user_id}")
        print(f"[*] User name: {self.user_name}")
        print(f"[*] Max posts: {self.max_posts}")
        print(f"[*] Crawl mode: {'video' if self.crawl_mode == VIDEO_MODE else 'image'}")
        print(f"[*] Output: {self.output_dir.resolve()}")
        print()
        await self._collect_posts()
        self.user_profile = extract_user_profile(
            self.posts,
            fallback_user_name=self.user_name,
            fallback_user_id=self.user_id,
        )
        self._filter_and_sort()
        if not self.selected_posts:
            print(f"[X] No {self._mode_label()} posts found!")
            return
        if self.crawl_mode == VIDEO_MODE:
            await cache_video_posts(self.selected_posts, self.output_dir)
        else:
            await download_image_posts(self.selected_posts, self.output_dir)
        self._summarize()

    async def _collect_posts(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser, context = await create_context(pw, self.cookie_str, self.headless)
            page = await context.new_page()
            try:
                await collect_all_posts(page, self.user_id, self.posts, self.max_posts)
            finally:
                await browser.close()

    def _filter_and_sort(self):
        matcher = is_video_post if self.crawl_mode == VIDEO_MODE else is_image_post
        self.selected_posts = [p for p in self.posts if matcher(p)]
        self.selected_posts.sort(key=lambda p: p.get("create_time", 0), reverse=True)
        print(f"[OK] {self._mode_label().capitalize()} posts found: {len(self.selected_posts)}")

    def _mode_label(self):
        return "video" if self.crawl_mode == VIDEO_MODE else "image"

    def _summarize(self):
        print()
        print("=" * 50)
        print("[OK] Crawl complete!")
        print(f"   Total posts scraped: {len(self.posts)}")
        print(f"   {self._mode_label().capitalize()} posts:        {len(self.selected_posts)}")
        print(f"   Output directory:    {self.output_dir.resolve()}")
        print("=" * 50)


def main():
    load_dotenv()
    user_id = os.getenv("DOUYIN_USER_ID", "").strip()
    if not user_id:
        print("Error: DOUYIN_USER_ID not set")
        sys.exit(1)
    cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    max_posts = int(os.getenv("MAX_POSTS", "50"))
    output_dir = os.getenv("OUTPUT_DIR", "./output")
    headless = os.getenv("HEADLESS", "true").lower() != "false"
    user_name = os.getenv("DOUYIN_USER_NAME", "").strip()
    crawl_mode = os.getenv("CRAWL_MODE", IMAGE_MODE).strip().lower() or IMAGE_MODE
    crawler = DouyinCrawler(
        user_id=user_id,
        user_name=user_name,
        cookie_str=cookie,
        max_posts=max_posts,
        output_dir=output_dir,
        headless=headless,
        crawl_mode=crawl_mode,
    )
    asyncio.run(crawler.run())


if __name__ == "__main__":
    main()
