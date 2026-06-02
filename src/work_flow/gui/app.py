# -*- coding: utf-8 -*-
"""抖音爬虫 Web UI —— FastAPI 入口。"""

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.work_flow.gui.routers import home, user, favorites
from src.work_flow.gui.services.scanner import get_output_dir

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="抖音爬虫 Web UI", version="0.1.0")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["quote"] = lambda s: quote(str(s), safe="/")
templates.env.globals["asset_version"] = int((BASE_DIR / "static" / "css" / "style.css").stat().st_mtime)
app.state.templates = templates

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

_data_dir = get_output_dir()
if os.path.isdir(_data_dir):
    app.mount("/data", StaticFiles(directory=_data_dir), name="data")


app.include_router(home.router)
app.include_router(user.router, prefix="/user")
app.include_router(favorites.router, prefix="/favorites")


@app.on_event("startup")
async def startup():
    print(f"[WebUI] 数据根目录: {_data_dir}")
    print("[WebUI] 访问地址: http://127.0.0.1:8000")
