# -*- coding: utf-8 -*-
"""用户作品列表 / 作品详情路由。"""

import math
from urllib.parse import quote, urlencode
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.crawler.downloader import download_video_for_post
from src.work_flow.gui.services.scanner import Scanner

router = APIRouter()

PAGE_SIZE = 60


def _attach_media_sources(posts: list, data_prefix: str):
    for post in posts:
        post.motion_src = ""
        if getattr(post, "motion_downloaded", False) and getattr(post, "motion_file_name", ""):
            post.motion_src = f"{data_prefix}/{quote(post.dir_name)}/{quote(post.motion_file_name)}"
        elif getattr(post, "motion_url", ""):
            post.motion_src = post.motion_url


@router.get("/{user_dir}/", response_class=HTMLResponse)
async def user_posts(request: Request, user_dir: str, page: int = Query(1, ge=1)):
    scanner = Scanner()
    user = scanner.get_user(user_dir)
    if user is None:
        return request.app.state.templates.TemplateResponse(
            request, "404.html", {}, status_code=404
        )
    total = len(user.posts)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_posts = user.posts[start:start + PAGE_SIZE]
    data_prefix = scanner.compute_data_prefix(user_dir)
    _attach_media_sources(page_posts, data_prefix)
    return request.app.state.templates.TemplateResponse(
        request, "user.html", {
            "user": user, "posts": page_posts, "data_prefix": data_prefix,
            "page": page, "total_pages": total_pages, "total": total,
            "page_size": PAGE_SIZE,
        }
    )


@router.get("/{user_dir}/{post_dir}/", response_class=HTMLResponse)
async def post_detail(
    request: Request,
    user_dir: str,
    post_dir: str,
    message: str | None = Query(None),
    message_kind: str = Query("success"),
):
    scanner = Scanner()
    post = scanner.get_post(user_dir, post_dir)
    if post is None:
        return request.app.state.templates.TemplateResponse(
            request, "404.html", {}, status_code=404
        )
    images = scanner.get_images(user_dir, post_dir)
    motion_sources = scanner.get_motion_sources(user_dir, post_dir)
    info_text = scanner.get_info_text(user_dir, post_dir)
    data_prefix = scanner.compute_data_prefix(user_dir)
    _attach_media_sources([post], data_prefix)
    resolved_motion_sources = [
        f"{data_prefix}/{quote(post.dir_name)}/{quote(src)}" if src and not src.startswith(("http://", "https://")) else src
        for src in motion_sources
    ]
    return request.app.state.templates.TemplateResponse(
        request, "post.html", {
            "post": post, "images": images,
            "motion_sources": resolved_motion_sources,
            "info_text": info_text, "data_prefix": data_prefix,
            "user_dir": user_dir,
            "message": message,
            "message_kind": message_kind,
        }
    )


@router.get("/{user_dir}/{post_dir}/json")
async def post_json(user_dir: str, post_dir: str):
    """返回作品元数据 JSON（供幻灯片预加载）"""
    scanner = Scanner()
    post = scanner.get_post(user_dir, post_dir)
    if post is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    images = scanner.get_images(user_dir, post_dir)
    motion_sources = scanner.get_motion_sources(user_dir, post_dir)
    info_text = scanner.get_info_text(user_dir, post_dir)
    data_prefix = scanner.compute_data_prefix(user_dir)
    quoted_post_dir = quote(post.dir_name, safe="")
    return {
        "title": post.title,
        "date_str": post.date_str,
        "image_count": post.image_count,
        "media_kind": post.media_kind,
        "motion_available": post.motion_available,
        "motion_src": getattr(post, "motion_src", ""),
        "motion_sources": [
            f"{data_prefix}/{quoted_post_dir}/{quote(src, safe='')}"
            if src and not src.startswith(("http://", "https://")) else src
            for src in motion_sources
        ],
        "video_downloaded": post.video_downloaded,
        "images": [
            f"{data_prefix}/{quoted_post_dir}/{quote(img, safe='')}"
            for img in images
        ],
        "info_text": info_text,
        "detail_href": f"/user/{quote(user_dir, safe='')}/{quoted_post_dir}/",
        "download_video_href": (
            f"/user/{quote(user_dir, safe='')}/{quoted_post_dir}/download-video"
            if post.media_kind == "video" else ""
        ),
    }


@router.post("/{user_dir}/{post_dir}/download-video")
async def download_video(user_dir: str, post_dir: str):
    scanner = Scanner()
    post_path = scanner.resolve_post_path(user_dir, post_dir)
    if post_path is None:
        return RedirectResponse(url=f"/user/{quote(user_dir)}/", status_code=303)
    try:
        await download_video_for_post(post_path)
        query = urlencode({"message": "视频已下载", "message_kind": "success"})
    except Exception as exc:
        query = urlencode({"message": f"视频下载失败: {exc}", "message_kind": "error"})
    target = f"/user/{quote(user_dir)}/{quote(post_dir)}/?{query}"
    return RedirectResponse(url=target, status_code=303)
