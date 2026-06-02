# -*- coding: utf-8 -*-
"""全局收藏页路由。"""

from dataclasses import asdict
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.work_flow.gui.services.scanner import Scanner

router = APIRouter()


def _serialize_post(post, data_prefix: str, user_href: str):
    data = asdict(post)
    motion_src = ""
    if post.motion_downloaded and post.motion_file_name:
        motion_src = f"{data_prefix}/{quote(post.dir_name, safe='')}/{quote(post.motion_file_name, safe='')}"
    elif post.motion_url:
        motion_src = post.motion_url
    media_file = post.thumbnail if post.thumbnail else post.first_image
    data["detail_href"] = f"{user_href}{quote(post.dir_name, safe='')}/"
    data["image_src"] = f"{data_prefix}/{quote(post.dir_name, safe='')}/{quote(media_file, safe='')}" if media_file else ""
    data["motion_src"] = motion_src
    return data


@router.get("/", response_class=HTMLResponse)
async def favorites_page(request: Request):
    scanner = Scanner()
    all_users = scanner.scan_users()

    favs_by_user = []
    for user in all_users:
        data_prefix = scanner.compute_data_prefix(user.dir_name)
        user_href = f"/user/{quote(user.dir_name, safe='')}/"
        favs_by_user.append({
            "dir_name": user.dir_name,
            "user_href": user_href,
            "data_prefix": data_prefix,
            "posts": [_serialize_post(p, data_prefix, user_href) for p in user.posts],
        })

    return request.app.state.templates.TemplateResponse(
        request, "favorites.html", {
            "users": favs_by_user,
        }
    )
