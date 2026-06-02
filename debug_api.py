import asyncio, json, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

async def main():
    from playwright.async_api import async_playwright

    cookie_str = os.getenv("DOUYIN_COOKIE", "").strip()
    user_id = os.getenv("DOUYIN_USER_ID", "").strip()

    captured_url = None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        if cookie_str:
            from src.crawler.browser import parse_cookies
            await context.add_cookies(parse_cookies(cookie_str))

        page = await context.new_page()

        async def on_response(response):
            nonlocal captured_url
            url = response.url
            if "/aweme/v1/web/aweme/post" in url and response.status == 200:
                if captured_url is None:
                    captured_url = url
                    try:
                        body = await response.json()
                        al = body.get("aweme_list", [])
                        print(f"aweme_count={len(al)}, has_more={body.get('has_more')}, max_cursor={body.get('max_cursor')}")
                        if al:
                            print(f"first: media_type={al[0].get('media_type')}, desc={(al[0].get('desc') or '')[:40]}")
                    except Exception as e:
                        print(f"error: {e}")

        page.on("response", on_response)

        await page.goto(f"https://www.douyin.com/user/{user_id}", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(10)

        if captured_url:
            Path("debug_post_url.txt").write_text(captured_url, encoding="utf-8")
            print(f"URL saved to debug_post_url.txt")
        else:
            print("NOT captured!")

        await browser.close()

asyncio.run(main())
