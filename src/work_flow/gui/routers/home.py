# -*- coding: utf-8 -*-
"""首页 / 配置 / 爬虫路由。"""

import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from src.work_flow.gui.services.scanner import Scanner, get_output_dir
from src.work_flow.gui.services.crawl_manager import crawl_task_manager
from src.work_flow.gui.services.profile_store import ProfileStore

router = APIRouter()


def _build_task_summary(tasks: list[dict]) -> dict:
    counts = {"running": 0, "completed": 0, "failed": 0}
    for task in tasks:
        status = str(task.get("status") or "")
        if status in counts:
            counts[status] += 1
    recent = tasks[-1] if tasks else None
    return {"counts": counts, "recent": recent}


def _default_options() -> dict[str, str]:
    return {
        "user_name": os.getenv("DOUYIN_USER_NAME", ""),
        "user_id": os.getenv("DOUYIN_USER_ID", ""),
        "cookie": os.getenv("DOUYIN_COOKIE", ""),
        "crawl_mode": os.getenv("CRAWL_MODE", "image"),
        "max_posts": os.getenv("MAX_POSTS", "50"),
        "output_dir": os.getenv("OUTPUT_DIR", "./output"),
        "headless": os.getenv("HEADLESS", "true"),
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    scanner = Scanner()
    users = scanner.scan_users()
    output_dir = get_output_dir()
    defaults = _default_options()
    tasks = crawl_task_manager.list_tasks()
    task_summary = _build_task_summary(tasks)
    return request.app.state.templates.TemplateResponse(
        request, "home.html", {
            "users": users,
            "output_dir": output_dir,
            "defaults": defaults,
            "tasks": tasks,
            "task_summary": task_summary,
        }
    )


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    defaults = _default_options()
    profiles = ProfileStore(defaults["output_dir"]).list_profiles()
    tasks = crawl_task_manager.list_tasks()
    return request.app.state.templates.TemplateResponse(
        request, "config.html", {"defaults": defaults, "profiles": profiles, "tasks": tasks}
    )


@router.post("/crawl", response_class=HTMLResponse)
async def start_crawl(
    request: Request,
    user_name: str = Form(""),
    user_id: str = Form(...),
    cookie: str = Form(""),
    crawl_mode: str = Form("image"),
    max_posts: int = Form(50),
    output_dir: str = Form("./output"),
    headless: str = Form("true"),
):
    env_defaults = _default_options()
    cookie = cookie.strip() or env_defaults["cookie"]
    output_dir = output_dir.strip() or env_defaults["output_dir"]
    headless = headless.strip() or env_defaults["headless"]
    task = crawl_task_manager.start(
        user_name=user_name.strip(),
        user_id=user_id.strip(),
        cookie_str=cookie,
        crawl_mode=crawl_mode.strip().lower() or "image",
        max_posts=max_posts,
        output_dir=output_dir,
        headless=headless.lower() != "false",
    )
    defaults = {
        "user_name": user_name,
        "user_id": user_id,
        "cookie": cookie,
        "crawl_mode": crawl_mode,
        "max_posts": str(max_posts),
        "output_dir": output_dir,
        "headless": headless,
    }
    profiles = ProfileStore(output_dir).list_profiles()
    tasks = crawl_task_manager.list_tasks()
    mode_label = "视频封面缓存" if crawl_mode == "video" else "图片爬取"
    return request.app.state.templates.TemplateResponse(
        request, "config.html", {
            "defaults": defaults, "profiles": profiles, "tasks": tasks,
            "message": f"{mode_label}任务已启动! ID: {task['id']}"
        }
    )


@router.post("/profiles/delete", response_class=HTMLResponse)
async def delete_profile(
    request: Request,
    user_id: str = Form(...),
    output_dir: str = Form("./output"),
):
    defaults = _default_options()
    output_dir = output_dir.strip() or defaults["output_dir"]
    store = ProfileStore(output_dir)
    deleted = store.delete(user_id)
    profiles = store.list_profiles()
    tasks = crawl_task_manager.list_tasks()
    message = "爬取对象已删除" if deleted else "未找到要删除的爬取对象"
    return request.app.state.templates.TemplateResponse(
        request,
        "config.html",
        {
            "defaults": defaults,
            "profiles": profiles,
            "tasks": tasks,
            "message": message,
        },
    )
