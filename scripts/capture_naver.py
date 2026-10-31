from pathlib import Path

from playwright.sync_api import sync_playwright


output_path = Path(__file__).parents[1] / "naver_homepage.png"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1024}, device_scale_factor=1)
    page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(2_000)
    page.screenshot(path=str(output_path), full_page=True)
    browser.close()

print(output_path)
