"""Verify the static portfolio and the local keyword page using synthetic data."""

from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto("http://127.0.0.1:8522/")
        page.locator("#rows tr").first.wait_for()
        assert page.locator("#rows tr").count() == 4
        assert page.locator("#up").inner_text() == "1"
        assert page.locator("#missing").inner_text() == "1"
        page.screenshot(path=str(ROOT / "docs/showcase-desktop.png"), full_page=True)
        page.get_by_role("button", name="SP 广告位", exact=True).click()
        assert page.locator("#missing").inner_text() == "0"
        page.locator("#search").fill("no matching term")
        assert "没有匹配" in page.locator("#rows").inner_text()
        page.locator("#search").fill("")
        page.locator("#asin").select_option("B0DEMO0002")
        assert page.locator("#rows tr").count() == 4
        with page.expect_download() as download:
            page.get_by_role("link", name="↓ 下载示例日报", exact=True).click()
        book = load_workbook(BytesIO(download.value.path().read_bytes()))
        assert "每日排名" in book.sheetnames
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(ROOT / "docs/showcase-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.goto("http://127.0.0.1:8521/")
        page.get_by_test_id("stSidebar").get_by_text("关键词日报", exact=True).click()
        page.get_by_text("下载关键词日报 Excel", exact=True).wait_for()
        assert page.get_by_test_id("stException").count() == 0
        page.get_by_role("heading", name="亚马逊运营工作台", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(ROOT / "docs/keyword-workbench.png"), full_page=True)
        browser.close()
    print("Showcase verified: filters, organic/SP split, ASIN switch, Excel download, mobile width and local keyword module.")


if __name__ == "__main__":
    main()
