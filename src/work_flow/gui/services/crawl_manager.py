# -*- coding: utf-8 -*-
"""爬虫任务管理器 —— 后台异步执行爬虫。"""

import asyncio
import sys
import threading
import uuid
from datetime import datetime

from src.work_flow.gui.services.profile_store import ProfileStore


class CrawlTaskManager:

    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._threads: dict[str, threading.Thread] = {}

    def start(self, user_name: str = "", user_id: str = "", cookie_str: str = "",
              max_posts: int = 50, output_dir: str = "./output", headless: bool = True,
              crawl_mode: str = "image") -> dict:
        task_id = uuid.uuid4().hex[:8]
        display = user_name or user_id
        task = {
            "id": task_id,
            "user_id": display,
            "crawl_mode": crawl_mode,
            "status": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": "爬虫启动中...",
        }
        self._tasks[task_id] = task

        def _run():
            # Windows 需要 ProactorEventLoop 以支持子进程（Playwright 依赖）
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from src.douyin_crawler import DouyinCrawler
                crawler = DouyinCrawler(
                    user_id=user_id,
                    user_name=user_name,
                    cookie_str=cookie_str,
                    max_posts=max_posts,
                    output_dir=output_dir,
                    headless=headless,
                    crawl_mode=crawl_mode,
                )
                loop.run_until_complete(crawler.run())
                profile = ProfileStore(output_dir).upsert(
                    user_id=user_id,
                    user_name=crawler.user_profile.get("user_name", user_name),
                    dir_name=crawler.output_dir.name,
                    avatar_url=crawler.user_profile.get("avatar_url", ""),
                    output_dir=output_dir,
                )
                task["status"] = "completed"
                task["user_id"] = profile.user_name
                if crawl_mode == "video":
                    task["message"] = f"缓存完成! 共缓存 {len(crawler.selected_posts)} 个视频封面"
                else:
                    task["message"] = f"爬取完成! 共下载 {len(crawler.selected_posts)} 个图片作品"
            except Exception as exc:
                task["status"] = "failed"
                task["message"] = f"爬取失败: {exc}"
            finally:
                loop.close()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        self._threads[task_id] = thread
        return task

    def list_tasks(self) -> list[dict]:
        return list(self._tasks.values())


crawl_task_manager = CrawlTaskManager()
