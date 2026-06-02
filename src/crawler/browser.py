"""浏览器管理：启动 Playwright、注入 Cookie、导航、API 拦截、cursor 分页。"""

import asyncio
import json as _json
import re
import urllib.parse as _ul


POST_API_PATTERN = re.compile(r"/aweme/v1/web/aweme/post")
INITIAL_API_WAIT_SECONDS = 12
FALLBACK_API_WAIT_SECONDS = 18


async def ensure_browser_installed() -> None:
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
    except Exception:
        print("[+] 首次使用，正在安装 Playwright 浏览器...")
        print("   请手动运行: playwright install chromium")
        import sys
        sys.exit(1)


def parse_cookies(cookie_str: str) -> list[dict]:
    cookies: list[dict] = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        key, _, val = item.partition("=")
        key = key.strip()
        val = val.strip()
        if key and val:
            cookies.append({
                "name": key,
                "value": val,
                "domain": ".douyin.com",
                "path": "/",
            })
    return cookies


def _build_ua() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )


async def create_context(playwright, cookie_str: str, headless: bool):
    browser = await playwright.chromium.launch(headless=headless)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=_build_ua(),
    )
    if cookie_str:
        cookies = parse_cookies(cookie_str)
        await context.add_cookies(cookies)
        print(f"[+] 已注入 {len(cookies)} 条 Cookie")
    else:
        print("[WARN] 未提供 Cookie，可能无法获取数据")
    return browser, context


async def navigate_to_user(page, user_id: str) -> None:
    url = f"https://www.douyin.com/user/{user_id}"
    print(f"[*] 导航到: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    print("[*] 页面加载完成")


async def _click_post_tab(page) -> bool:

    selectors = [
        "[data-e2e='user-post-tab']",
        ".route-tab-list >> text=作品",
        "[class*='tab']:has-text('作品')",
        "[role='tab']:has-text('作品')",
        "[role='tab']:has-text('视频')",
        "text=作品",
        "text=视频",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                print(f"[+] 已点击 Tab: {sel}")
                return True
        except Exception:
            continue
    try:
        title = await page.title()
    except Exception:
        title = "unknown"
    print(f"[WARN] 未找到 '作品' Tab (title={title})")
    return False


async def _trigger_post_loading(page) -> None:
    clicked = await _click_post_tab(page)
    if clicked:
        await asyncio.sleep(2)
    for idx in range(3):
        try:
            await page.mouse.wheel(0, 1200)
        except Exception:
            await page.evaluate("window.scrollBy(0, 1200)")
        print(f"[*] 尝试滚动触发作品请求 #{idx + 1}")
        await asyncio.sleep(1.5)


def _extract_api_info(url: str) -> dict:
    parsed = _ul.urlparse(url)
    params = dict(_ul.parse_qsl(parsed.query))
    params.pop("max_cursor", None)
    params.pop("min_cursor", None)
    params.pop("count", None)
    return {"base_url": f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "params": params}


_BROWSER_FETCH_JS = """(
async (params) => {
    const { baseUrl, queryParams, cursor, count } = params;
    const qp = new URLSearchParams(queryParams);
    qp.set('max_cursor', cursor);
    qp.set('count', count);
    const url = baseUrl + '?' + qp.toString();
    const resp = await fetch(url, { credentials: 'include' });
    if (!resp.ok) {
        return { error: true, status: resp.status };
    }
    const data = await resp.json();
    return {
        error: false,
        hasMore: data.has_more === 1,
        maxCursor: data.max_cursor || 0,
        awemeList: (data.aweme_list || []).map(a => ({
            aweme_id: a.aweme_id,
            desc: a.desc,
            create_time: a.create_time,
            media_type: a.media_type,
            aweme_type: a.aweme_type,
            images: a.images,
            video: a.video,
            author: a.author ? {
                nickname: a.author.nickname,
                unique_id: a.author.unique_id,
                short_id: a.author.short_id,
                avatar_thumb: a.author.avatar_thumb,
                avatar_medium: a.author.avatar_medium,
                avatar_larger: a.author.avatar_larger,
                avatar_300x300: a.author.avatar_300x300,
            } : null,
        })),
    };
}
)"""


async def collect_all_posts(page, user_id: str, posts: list[dict], max_posts: int) -> None:
    seen_ids: set = set()
    api_info: dict | None = None
    has_more = True
    cursor = 0
    first_event = asyncio.Event()
    api_failure = False

    async def on_response(response):
        nonlocal api_info, has_more, cursor, api_failure
        if first_event.is_set():
            return
        if not POST_API_PATTERN.search(response.url):
            return
        if response.status != 200:
            api_failure = True
            first_event.set()
            return
        try:
            body = await response.json()
        except Exception:
            api_failure = True
            first_event.set()
            return
        aweme_list = body.get("aweme_list", [])
        if not aweme_list:
            api_failure = True
            first_event.set()
            return
        api_info = _extract_api_info(response.url)
        has_more = body.get("has_more", 0) == 1
        cursor = body.get("max_cursor", 0)
        for a in aweme_list:
            aid = a.get("aweme_id")
            if aid and aid not in seen_ids:
                seen_ids.add(aid)
                posts.append(a)
        print(f" [page 1] 截获 {len(aweme_list)} 条作品, cursor={cursor}, has_more={has_more}")
        first_event.set()

    page.on("response", on_response)

    # 监听器就绪，开始导航
    await navigate_to_user(page, user_id)
    try:
        await asyncio.wait_for(first_event.wait(), timeout=INITIAL_API_WAIT_SECONDS)
    except asyncio.TimeoutError:
        print("[WARN] 首屏未截获到作品 API，尝试点击 Tab / 滚动触发")
        await _trigger_post_loading(page)
        try:
            await asyncio.wait_for(first_event.wait(), timeout=FALLBACK_API_WAIT_SECONDS)
        except asyncio.TimeoutError:
            title = await page.title()
            print(f"[WARN] 未截获到作品 API 响应，请检查 Cookie / 用户 ID / 页面状态 (title={title}, url={page.url})")
            return

    if api_failure or not api_info:
        print("[WARN] API 响应异常或返回空数据")
        return

    page_num = 1
    max_pages = 100

    while has_more and len(posts) < max_posts and page_num < max_pages:
        page_num += 1
        fetch_args = _json.dumps({
            "baseUrl": api_info["base_url"],
            "queryParams": api_info["params"],
            "cursor": cursor,
            "count": 20,
        }, ensure_ascii=True)
        try:
            result = await page.evaluate(f"{_BROWSER_FETCH_JS}({fetch_args})")
        except Exception as e:
            print(f" [page {page_num}] fetch 失败: {e}")
            break

        if result.get("error"):
            print(f" [page {page_num}] HTTP {result.get('status')} 请求失败")
            break

        aweme_list = result.get("awemeList", [])
        has_more = result.get("hasMore", False)
        cursor = result.get("maxCursor", 0)

        new_count = 0
        for a in aweme_list:
            aid = a.get("aweme_id")
            if aid and aid not in seen_ids:
                seen_ids.add(aid)
                posts.append(a)
                new_count += 1

        print(f" [page {page_num}] 获取 {len(aweme_list)} 条作品(新增 {new_count}), cursor={cursor}, has_more={has_more}")
        if not aweme_list:
            break
        await asyncio.sleep(0.5)

    print(f" [Done] 共计爬取 {len(posts)} 条作品")
