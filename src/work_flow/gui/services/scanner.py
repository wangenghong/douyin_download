# -*- coding: utf-8 -*-
"""文件系统扫描服务 —— 从数据目录读取用户/作品结构。

支持两种数据布局：
  A) OUTPUT_DIR/用户/作品集/img_XX.jpg     → 多用户模式
  B) OUTPUT_DIR/作品集/img_XX.jpg           → 单用户模式（自动将 OUTPUT_DIR 视为一个用户）
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import quote

from src.crawler.downloader import (
    MANIFEST_FILE,
    MOTION_FILE_NAME,
    THUMB_FILE_NAME,
    VIDEO_FILE_NAME,
)
from src.crawler.models import is_audio_asset_url
from src.work_flow.gui.services.profile_store import ProfileStore


@dataclass
class PostInfo:
    """作品集目录信息。"""
    dir_name: str
    title: str = ''
    date_str: str = ''
    image_count: int = 0
    first_image: str = ""
    thumbnail: str = ""
    media_kind: str = "image"
    motion_available: bool = False
    motion_downloaded: bool = False
    motion_files: list[str] = field(default_factory=list)
    motion_file_name: str = ""
    motion_url: str = ""
    video_downloaded: bool = False
    video_file_name: str = ""


@dataclass
class UserDirInfo:
    """用户目录信息。"""
    dir_name: str
    display_name: str = ""
    user_id: str = ""
    avatar_url: str = ""
    post_count: int = 0
    posts: list[PostInfo] = field(default_factory=list)


class Scanner:
    """扫描 OUTPUT_DIR 下的用户目录和作品集。"""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(
            output_dir or os.getenv("OUTPUT_DIR", "./output")
        ).resolve()
        self.profile_store = ProfileStore(str(self.output_dir))

    def scan_users(self) -> list[UserDirInfo]:
        """扫描所有用户，自动检测单用户/多用户模式。"""
        if not self.output_dir.exists():
            return []
        # 检测：如果 OUTPUT_DIR 本身直接包含作品目录（有 img_*.jpg）
        # 则为单用户模式；否则为多用户模式
        if self._contains_post_dirs(self.output_dir):
            user = self._scan_user(self.output_dir)
            if user.post_count > 0:
                return [user]
            return []
        users: list[UserDirInfo] = []
        for entry in sorted(self.output_dir.iterdir(), reverse=True):
            if entry.is_dir():
                user = self._scan_user(entry)
                if user.post_count > 0:
                    users.append(user)
        return users

    def get_user(self, user_dir: str) -> UserDirInfo | None:
        # 直接路径匹配
        path = self.output_dir / user_dir
        if path.is_dir():
            return self._scan_user(path)
        # 单用户模式下，user_dir 等于 OUTPUT_DIR 名称
        if self._contains_post_dirs(self.output_dir) and user_dir == self.output_dir.name:
            return self._scan_user(self.output_dir)
        return None

    def get_post(self, user_dir: str, post_dir: str) -> PostInfo | None:
        path = self.output_dir / user_dir / post_dir
        if path.is_dir():
            return self._scan_post(path)
        # 单用户模式下，跳过 user_dir 层级
        if self._contains_post_dirs(self.output_dir) and user_dir == self.output_dir.name:
            alt_path = self.output_dir / post_dir
            if alt_path.is_dir():
                return self._scan_post(alt_path)
        return None

    def get_images(self, user_dir: str, post_dir: str) -> list[str]:
        path = self.resolve_post_path(user_dir, post_dir)
        if path is None:
            return []
        images = sorted(f for f in os.listdir(path) if f.startswith("img_") and f.endswith(".jpg"))
        if images:
            return images
        if (path / THUMB_FILE_NAME).exists():
            return [THUMB_FILE_NAME]
        return []

    def get_info_text(self, user_dir: str, post_dir: str) -> str:
        path = self.resolve_post_path(user_dir, post_dir)
        if path is None:
            return ""
        info_path = path / "info.txt"
        if info_path.exists():
            return info_path.read_text(encoding="utf-8")
        return ""

    def get_motion_sources(self, user_dir: str, post_dir: str) -> list[str]:
        path = self.resolve_post_path(user_dir, post_dir)
        if path is None:
            return []
        images = self.get_images(user_dir, post_dir)
        if not images:
            return []
        manifest = self._load_manifest(path)
        motion_urls = self._motion_urls_from_manifest(
            manifest,
            str(manifest.get("media_kind") or "image"),
            len(images),
        )
        sources = list(motion_urls)
        indexed_files = self._indexed_motion_files(path, len(images))
        for index, file_name in indexed_files.items():
            if 0 <= index < len(sources):
                sources[index] = file_name
        if any(sources):
            return sources
        legacy_motion = path / MOTION_FILE_NAME
        if legacy_motion.exists() and self._is_video_motion_file(legacy_motion):
            legacy_index = next((i for i, url in enumerate(motion_urls) if url), 0)
            sources[legacy_index] = MOTION_FILE_NAME
            return sources
        return motion_urls

    def resolve_post_path(self, user_dir: str, post_dir: str) -> Path | None:
        """解析作品目录路径，兼容单/多用户模式。"""
        # 优先多用户路径
        path = self.output_dir / user_dir / post_dir
        if path.is_dir():
            return path
        # 单用户模式下跳过 user 层级
        if self._contains_post_dirs(self.output_dir) and user_dir == self.output_dir.name:
            alt = self.output_dir / post_dir
            if alt.is_dir():
                return alt
        return None

    def _scan_user(self, path: Path) -> UserDirInfo:
        profile = self.profile_store.get_by_dir_name(path.name)
        user = UserDirInfo(
            dir_name=path.name,
            display_name=profile.user_name if profile else path.name,
            user_id=profile.user_id if profile else "",
            avatar_url=profile.avatar_url if profile else "",
        )
        for entry in sorted(path.iterdir(), reverse=True):
            if entry.is_dir() and self._is_post_dir(entry):
                post = self._scan_post(entry)
                if post.image_count > 0:
                    user.posts.append(post)
        user.post_count = len(user.posts)
        return user

    def _scan_post(self, path: Path) -> PostInfo:
        info = PostInfo(dir_name=path.name)
        parts = path.name.split("_", 1)
        info.date_str = parts[0] if parts else ""
        info.title = parts[1] if len(parts) > 1 else path.name
        manifest = self._load_manifest(path)
        images = sorted(
            [f for f in os.listdir(path) if f.startswith("img_") and f.endswith(".jpg")],
            reverse=True,
        )
        info.media_kind = str(manifest.get("media_kind") or ("video" if (path / THUMB_FILE_NAME).exists() and not images else "image"))
        info.image_count = len(images) if images else (1 if (path / THUMB_FILE_NAME).exists() else 0)
        if images:
            info.first_image = images[-1]
        elif (path / THUMB_FILE_NAME).exists():
            info.first_image = THUMB_FILE_NAME
        if (path / THUMB_FILE_NAME).exists():
            info.thumbnail = THUMB_FILE_NAME
        motion_urls = self._motion_urls_from_manifest(manifest, info.media_kind, len(images))
        info.motion_files = list(self._indexed_motion_files(path, len(images)).values())
        legacy_motion = path / MOTION_FILE_NAME
        if not info.motion_files and legacy_motion.exists() and self._is_video_motion_file(legacy_motion):
            info.motion_files = [MOTION_FILE_NAME]
        info.motion_downloaded = bool(info.motion_files)
        if info.motion_downloaded:
            info.motion_available = True
            info.motion_file_name = info.motion_files[0]
        else:
            info.motion_url = next((url for url in motion_urls if url), "")
            info.motion_available = bool(info.motion_url)
        info.video_downloaded = (path / VIDEO_FILE_NAME).exists()
        if info.video_downloaded:
            info.video_file_name = VIDEO_FILE_NAME
        return info

    @staticmethod
    def _is_post_dir(path: Path) -> bool:
        for f in os.listdir(path):
            if (f.startswith("img_") and f.endswith(".jpg")) or f in {
                THUMB_FILE_NAME,
                MOTION_FILE_NAME,
                MANIFEST_FILE,
            }:
                return True
        return False

    @staticmethod
    def _motion_url_from_manifest(manifest: dict, media_kind: str) -> str:
        if media_kind != "image":
            return ""
        motion_url = str(manifest.get("motion_url") or "").strip()
        if not motion_url or is_audio_asset_url(motion_url):
            return ""
        return motion_url

    @classmethod
    def _motion_urls_from_manifest(cls, manifest: dict, media_kind: str, image_count: int) -> list[str]:
        if media_kind != "image":
            return []
        raw_urls = manifest.get("motion_urls")
        if isinstance(raw_urls, list):
            motion_urls = [str(url or "").strip() for url in raw_urls]
            motion_urls = [url if url and not is_audio_asset_url(url) else "" for url in motion_urls]
            if image_count and len(motion_urls) < image_count:
                motion_urls.extend([""] * (image_count - len(motion_urls)))
            return motion_urls[:image_count] if image_count else motion_urls
        legacy_url = cls._motion_url_from_manifest(manifest, media_kind)
        if not image_count:
            return [legacy_url] if legacy_url else []
        motion_urls = [""] * image_count
        if legacy_url:
            motion_urls[0] = legacy_url
        return motion_urls

    @classmethod
    def _indexed_motion_files(cls, path: Path, image_count: int) -> dict[int, str]:
        indexed_files: dict[int, str] = {}
        for index in range(1, image_count + 1):
            file_name = f"motion_{index:02d}.mp4"
            motion_path = path / file_name
            if motion_path.exists() and cls._is_video_motion_file(motion_path):
                indexed_files[index - 1] = file_name
        return indexed_files

    @staticmethod
    def _is_video_motion_file(path: Path) -> bool:
        try:
            header = path.read_bytes()[:16]
        except OSError:
            return False
        return b"ftypM4A" not in header

    @staticmethod
    def _contains_post_dirs(path: Path) -> bool:
        """检测路径是否直接包含作品目录（非用户目录层级）。"""
        if not path.is_dir():
            return False
        for entry in os.listdir(path):
            entry_path = path / entry
            if entry_path.is_dir() and Scanner._is_post_dir(entry_path):
                return True
        return False


    def compute_data_prefix(self, user_dir: str) -> str:
        """计算模板中 /data URL 前缀，兼容单/多用户模式。"""
        if self._contains_post_dirs(self.output_dir) and user_dir == self.output_dir.name:
            return "/data"
        return f"/data/{quote(user_dir, safe='')}"

    @staticmethod
    def _load_manifest(path: Path) -> dict:
        manifest_path = path / MANIFEST_FILE
        if not manifest_path.exists():
            return {}
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


def get_output_dir() -> str:
    return str(Path(os.getenv("OUTPUT_DIR", "./output")).resolve())
