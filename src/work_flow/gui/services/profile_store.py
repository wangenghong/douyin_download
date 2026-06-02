# -*- coding: utf-8 -*-
"""Persist crawled Douyin user profiles for one-click recrawls."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from src.crawler.models import sanitize_filename

PROFILE_FILE = ".douyin_profiles.json"


@dataclass
class SavedProfile:
    user_id: str
    user_name: str
    dir_name: str
    avatar_url: str = ""
    output_dir: str = "./output"
    updated_at: str = ""


class ProfileStore:
    """Small JSON-backed store under OUTPUT_DIR."""

    def __init__(self, output_dir: str | None = None):
        root = output_dir or os.getenv("OUTPUT_DIR", "./output")
        self.output_dir = Path(root).resolve()
        self.path = self.output_dir / PROFILE_FILE

    def list_profiles(self) -> list[SavedProfile]:
        profiles = list(self._load().values())
        return sorted(profiles, key=lambda item: item.updated_at, reverse=True)

    def get_by_dir_name(self, dir_name: str) -> SavedProfile | None:
        for profile in self._load().values():
            if profile.dir_name == dir_name:
                return profile
        return None

    def delete(self, user_id: str) -> bool:
        cleaned_user_id = user_id.strip()
        if not cleaned_user_id:
            return False
        profiles = self._load()
        if cleaned_user_id not in profiles:
            return False
        profiles.pop(cleaned_user_id, None)
        self._save(profiles)
        return True

    def upsert(
        self,
        user_id: str,
        user_name: str,
        dir_name: str = "",
        avatar_url: str = "",
        output_dir: str = "",
    ) -> SavedProfile:
        cleaned_user_id = user_id.strip()
        if not cleaned_user_id:
            raise ValueError("user_id is required")
        profiles = self._load()
        previous = profiles.get(cleaned_user_id)
        profile = SavedProfile(
            user_id=cleaned_user_id,
            user_name=self._pick(user_name, previous.user_name if previous else "", cleaned_user_id),
            dir_name=self._pick(dir_name, previous.dir_name if previous else "", sanitize_filename(user_name or cleaned_user_id)),
            avatar_url=self._pick(avatar_url, previous.avatar_url if previous else ""),
            output_dir=self._pick(output_dir, previous.output_dir if previous else "", str(self.output_dir)),
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        profiles[cleaned_user_id] = profile
        self._save(profiles)
        return profile

    def _load(self) -> dict[str, SavedProfile]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        items = raw.get("profiles", []) if isinstance(raw, dict) else []
        return {
            profile.user_id: profile
            for profile in (self._coerce(item) for item in items)
            if profile is not None
        }

    def _save(self, profiles: dict[str, SavedProfile]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        data = {"profiles": [asdict(item) for item in profiles.values()]}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _coerce(item: object) -> SavedProfile | None:
        if not isinstance(item, dict):
            return None
        user_id = str(item.get("user_id", "")).strip()
        if not user_id:
            return None
        return SavedProfile(
            user_id=user_id,
            user_name=str(item.get("user_name") or user_id),
            dir_name=str(item.get("dir_name") or sanitize_filename(user_id)),
            avatar_url=str(item.get("avatar_url") or ""),
            output_dir=str(item.get("output_dir") or "./output"),
            updated_at=str(item.get("updated_at") or ""),
        )

    @staticmethod
    def _pick(*values: str) -> str:
        for value in values:
            cleaned = (value or "").strip()
            if cleaned:
                return cleaned
        return ""
