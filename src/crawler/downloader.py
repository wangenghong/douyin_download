"""图片下载器（httpx 异步）。"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

from .models import (
    IMAGE_MODE,
    VIDEO_MODE,
    build_info_text,
    build_post_manifest,
    parse_datetime,
    sanitize_filename,
)

sys.stdout.reconfigure(encoding="utf-8")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

MANIFEST_FILE = "post.json"
THUMB_FILE_NAME = "thumb.jpg"
VIDEO_FILE_NAME = "video.mp4"
MOTION_FILE_NAME = "motion.mp4"


def _output_dir(post: dict, base_dir: Path) -> Path:
    """构建作品输出子目录: output/YYYY-MM-DD_Title/"""
    dt = parse_datetime(post)
    date_str = dt.strftime("%Y-%m-%d")
    title = sanitize_filename(post.get("desc", "untitled").strip())
    return base_dir / f"{date_str}_{title}"


async def _download_one(
    client: httpx.AsyncClient, url: str, dest: Path,
) -> bool:
    """下载单张图片，带 3 次重试。返回 True 表示成功。"""
    for attempt in range(3):
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return True
        except Exception:
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
    print(f"    !! 下载失败 {url}")
    return False


def _create_client():
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={"Referer": "https://www.douyin.com/", "User-Agent": _UA},
        follow_redirects=True,
    )


def _write_post_files(post: dict, post_dir: Path, media_kind: str) -> dict:
    manifest = build_post_manifest(post, media_kind)
    (post_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (post_dir / "info.txt").write_text(
        build_info_text(post, media_kind=media_kind),
        encoding="utf-8",
    )
    return manifest


def _resolve_post_dir(post: dict, base_dir: Path) -> Path:
    existing = _find_post_dir_by_aweme_id(post.get("aweme_id", ""), base_dir)
    return existing or _output_dir(post, base_dir)


def _find_post_dir_by_aweme_id(aweme_id: str, base_dir: Path) -> Path | None:
    aweme_id = str(aweme_id or "").strip()
    if not aweme_id or not base_dir.exists():
        return None
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        manifest = _load_manifest_or_empty(entry)
        if str(manifest.get("aweme_id") or "").strip() == aweme_id:
            return entry
    return None


def _load_manifest_or_empty(post_dir: Path) -> dict:
    manifest_path = post_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _image_post_complete(post_dir: Path, manifest: dict) -> bool:
    image_urls = manifest.get("image_urls", [])
    for index in range(1, len(image_urls) + 1):
        if not (post_dir / f"img_{index:02d}.jpg").exists():
            return False
    motion_urls = manifest.get("motion_urls", [])
    if isinstance(motion_urls, list) and any(motion_urls):
        for index, motion_url in enumerate(motion_urls, start=1):
            if str(motion_url or "").strip():
                if not (post_dir / _motion_file_name(index)).exists():
                    return False
        return True
    motion_url = str(manifest.get("motion_url") or "").strip()
    return not motion_url or (post_dir / MOTION_FILE_NAME).exists()


def _video_post_complete(post_dir: Path, manifest: dict) -> bool:
    cover_url = str(manifest.get("cover_url") or "").strip()
    return not cover_url or (post_dir / THUMB_FILE_NAME).exists()


def _status_label(was_existing: bool, was_complete: bool) -> str:
    if was_complete:
        return "[SKIP]"
    return "[RESUME]" if was_existing else "[OK]"


async def download_image_posts(image_posts: list[dict], output_dir: Path) -> None:
    """按排序顺序下载所有图文作品的图片与元数据。"""
    async with _create_client() as client:
        for idx, post in enumerate(image_posts, start=1):
            post_dir = _resolve_post_dir(post, output_dir)
            was_existing = post_dir.exists()
            post_dir.mkdir(parents=True, exist_ok=True)

            manifest = _write_post_files(post, post_dir, IMAGE_MODE)
            was_complete = _image_post_complete(post_dir, manifest)
            image_urls = manifest.get("image_urls", [])
            for i, url in enumerate(image_urls, start=1):
                img_path = post_dir / f"img_{i:02d}.jpg"
                if not img_path.exists():
                    await _download_one(client, url, img_path)
            motion_urls = manifest.get("motion_urls", [])
            if isinstance(motion_urls, list) and any(motion_urls):
                for i, motion_url in enumerate(motion_urls, start=1):
                    motion_url = str(motion_url or "").strip()
                    if not motion_url:
                        continue
                    motion_path = post_dir / _motion_file_name(i)
                    if not motion_path.exists():
                        await _download_one(client, motion_url, motion_path)
            else:
                motion_url = str(manifest.get("motion_url") or "").strip()
                motion_path = post_dir / MOTION_FILE_NAME
                if motion_url and not motion_path.exists():
                    await _download_one(client, motion_url, motion_path)

            dt = parse_datetime(post)
            title = sanitize_filename(post.get("desc", ""), max_len=30)
            status = _status_label(was_existing, was_complete)
            print(
                f"{status} [{idx:02d}/{len(image_posts)}] "
                f"{dt.strftime('%Y-%m-%d')} | {title} "
                f"({len(image_urls)} 张)"
            )

            await asyncio.sleep(0.5)


async def cache_video_posts(video_posts: list[dict], output_dir: Path) -> None:
    """缓存视频作品封面与元数据，不自动下载视频文件。"""
    async with _create_client() as client:
        for idx, post in enumerate(video_posts, start=1):
            post_dir = _resolve_post_dir(post, output_dir)
            was_existing = post_dir.exists()
            post_dir.mkdir(parents=True, exist_ok=True)

            manifest = _write_post_files(post, post_dir, VIDEO_MODE)
            was_complete = _video_post_complete(post_dir, manifest)
            cover_url = str(manifest.get("cover_url") or "").strip()
            thumb_path = post_dir / THUMB_FILE_NAME
            if cover_url and not thumb_path.exists():
                await _download_one(client, cover_url, thumb_path)

            dt = parse_datetime(post)
            title = sanitize_filename(post.get("desc", ""), max_len=30)
            status = _status_label(was_existing, was_complete)
            print(
                f"{status} [{idx:02d}/{len(video_posts)}] "
                f"{dt.strftime('%Y-%m-%d')} | {title} "
                "(已缓存封面)"
            )

            await asyncio.sleep(0.3)


def load_post_manifest(post_dir: Path) -> dict:
    manifest_path = post_dir / MANIFEST_FILE
    if not manifest_path.exists():
        raise ValueError("缺少作品元数据")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


async def download_video_for_post(post_dir: Path) -> Path:
    """按缓存元数据手动下载单个视频文件。"""
    manifest = load_post_manifest(post_dir)
    if manifest.get("media_kind") != VIDEO_MODE:
        raise ValueError("该作品不是视频")
    video_url = str(manifest.get("video_url") or "").strip()
    if not video_url:
        raise ValueError("缺少视频下载地址")
    video_path = post_dir / VIDEO_FILE_NAME
    async with _create_client() as client:
        ok = await _download_one(client, video_url, video_path)
    if not ok:
        raise RuntimeError("视频下载失败")
    return video_path


async def download_all(image_posts: list[dict], output_dir: Path) -> None:
    """兼容旧调用，默认按图片模式下载。"""
    await download_image_posts(image_posts, output_dir)


def _motion_file_name(index: int) -> str:
    return f"motion_{index:02d}.mp4"
