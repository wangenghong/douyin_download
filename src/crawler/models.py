import re
from datetime import datetime

IMAGE_MODE = "image"
VIDEO_MODE = "video"
_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac")


def is_image_post(post):
    return bool(extract_image_urls(post))


def is_video_post(post):
    if is_image_post(post):
        return False
    return bool(extract_video_url(post))


def extract_image_urls(post):
    images = _as_list(post.get("images"))
    urls = []
    for img in images:
        if not isinstance(img, dict):
            continue
        candidates = []
        origin = img.get("origin_url") or {}
        if isinstance(origin, dict):
            candidates.extend(_as_list(origin.get("url_list")))
        candidates.extend(_as_list(img.get("url_list")))
        for u in candidates:
            if u and ("watermark" not in u.lower()):
                urls.append(u)
                break
        else:
            if candidates:
                urls.append(candidates[0])
    return urls


def extract_video_url(post):
    video = post.get("video") or {}
    candidates = []
    for key in ("play_addr", "download_addr"):
        value = video.get(key) or {}
        if isinstance(value, dict):
            candidates.extend(_as_list(value.get("url_list")))
    for bit_rate in _as_list(video.get("bit_rate")):
        play_addr = bit_rate.get("play_addr") if isinstance(bit_rate, dict) else None
        if isinstance(play_addr, dict):
            candidates.extend(_as_list(play_addr.get("url_list")))
    cleaned = [_normalize_video_url(url) for url in candidates if url]
    for url in cleaned:
        if "watermark=1" not in url.lower() and "playwm" not in url.lower():
            return url
    return cleaned[0] if cleaned else ""


def extract_motion_url(post):
    motion_urls = extract_motion_urls(post)
    return next((url for url in motion_urls if url), "")


def extract_motion_urls(post):
    motion_urls = []
    for image in _as_list(post.get("images")):
        if not isinstance(image, dict):
            motion_urls.append("")
            continue
        if not _is_live_photo_image(image):
            motion_urls.append("")
            continue
        motion_urls.append(_extract_image_video_url(image))
    return motion_urls


def extract_video_cover_url(post):
    video = post.get("video") or {}
    for key in ("dynamic_cover", "origin_cover", "cover", "animated_cover"):
        url = _first_url(video.get(key))
        if url:
            return url
    return ""


def parse_datetime(post):
    ts = post.get("create_time", 0)
    return datetime.fromtimestamp(ts)


def sanitize_filename(name, max_len=40):
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.rstrip(".")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned or "untitled"


def extract_user_profile(posts, fallback_user_name="", fallback_user_id=""):
    """Extract display metadata from crawled author payloads."""
    author = _first_author(posts)
    user_name = (fallback_user_name or "").strip()
    if not user_name and author:
        user_name = (
            author.get("nickname")
            or author.get("unique_id")
            or author.get("short_id")
            or ""
        ).strip()
    avatar_url = _extract_avatar_url(author) if author else ""
    return {
        "user_name": user_name or fallback_user_id,
        "avatar_url": avatar_url,
    }


def build_post_manifest(post, media_kind):
    dt = parse_datetime(post)
    return {
        "aweme_id": post.get("aweme_id", ""),
        "title": post.get("desc", "").strip(),
        "date_str": dt.strftime("%Y-%m-%d"),
        "create_time": post.get("create_time", 0),
        "media_kind": media_kind,
        "image_urls": extract_image_urls(post),
        "video_url": extract_video_url(post),
        "motion_url": extract_motion_url(post),
        "motion_urls": extract_motion_urls(post),
        "cover_url": extract_video_cover_url(post),
    }


def _first_author(posts):
    for post in posts:
        author = post.get("author")
        if isinstance(author, dict):
            return author
    return None


def _extract_avatar_url(author):
    for key in ("avatar_thumb", "avatar_medium", "avatar_larger", "avatar_300x300"):
        url = _first_url(author.get(key))
        if url:
            return url
    return ""


def _first_url(value):
    if isinstance(value, dict):
        urls = _as_list(value.get("url_list"))
        if urls:
            return next((u for u in urls if u), "")
        return value.get("url") or ""
    if isinstance(value, list):
        return next((u for u in value if u), "")
    return ""


def _as_list(value):
    return value if isinstance(value, list) else []


def _normalize_video_url(url):
    return url.replace("playwm", "play") if "playwm" in url else url


def _is_live_photo_image(image):
    return bool(image.get("live_photo_type")) and isinstance(image.get("video"), dict)


def _extract_image_video_url(image):
    video = image.get("video") or {}
    candidates = []
    for key in ("play_addr", "download_addr"):
        value = video.get(key) or {}
        if isinstance(value, dict):
            candidates.extend(_as_list(value.get("url_list")))
    cleaned = [_normalize_video_url(url) for url in candidates if url]
    for url in cleaned:
        if "watermark=1" not in url.lower() and "playwm" not in url.lower():
            return url
    return cleaned[0] if cleaned else ""


def is_audio_asset_url(url):
    return _is_audio_asset_url(url)


def _is_audio_asset_url(url):
    lowered = url.lower()
    return (
        lowered.endswith(_AUDIO_EXTENSIONS)
        or "/music/" in lowered
        or "ies-music" in lowered
    )


def build_info_text(post, media_kind=IMAGE_MODE):
    dt = parse_datetime(post)
    lines = [
        f"发布时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"作品ID:   {post.get('aweme_id', 'N/A')}",
        f"媒体类型: {'视频' if media_kind == VIDEO_MODE else '图片'}",
        "",
        "文案:",
        post.get("desc", "").strip(),
    ]
    if media_kind == VIDEO_MODE:
        lines.insert(3, "视频下载: 手动触发")
        lines.insert(3, "缓存内容: 封面图")
    else:
        lines.insert(2, f"图片数:   {len(_as_list(post.get('images')))}")
    return "\n".join(lines)
