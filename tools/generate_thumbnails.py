# -*- coding: utf-8 -*-
"""缩略图生成工具 —— 扫描 OUTPUT_DIR 下所有作品集，为 img_01.jpg 生成小尺寸缩略图。

生成: {post_dir}/thumb.jpg (宽 320px, JPEG quality 60)
用法: python tools/generate_thumbnails.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

THUMB_WIDTH = 320
THUMB_QUALITY = 60


def generate_thumbnail(src: Path, dest: Path) -> bool:
    """生成缩略图，返回 True 表示成功或已存在。"""
    if dest.exists():
        return True
    try:
        from PIL import Image
        img = Image.open(src)
        img = img.convert("RGB")
        w, h = img.size
        ratio = THUMB_WIDTH / w
        new_h = int(h * ratio)
        img = img.resize((THUMB_WIDTH, new_h), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=THUMB_QUALITY)
        return True
    except Exception as e:
        print(f"  !! 缩略图失败 {src}: {e}")
        return False


def scan_and_generate(output_dir: Path):
    done = 0
    skipped = 0
    if not output_dir.exists():
        print(f"目录不存在: {output_dir}")
        return
    for user_entry in sorted(output_dir.iterdir()):
        if not user_entry.is_dir():
            continue
        for post_entry in sorted(user_entry.iterdir()):
            if not post_entry.is_dir():
                continue
            img01 = post_entry / "img_01.jpg"
            if not img01.exists():
                continue
            thumb = post_entry / "thumb.jpg"
            if thumb.exists():
                skipped += 1
                continue
            if generate_thumbnail(img01, thumb):
                done += 1
                print(f"  OK {post_entry.name}/thumb.jpg")
    print(f"\nDone: {done} new, {skipped} existing")


def main():
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output")).resolve()
    print(f"Scan: {output_dir}")
    scan_and_generate(output_dir)


if __name__ == "__main__":
    main()
