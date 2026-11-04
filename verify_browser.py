"""Browser smoke check against the running local app; uses synthetic fixtures only."""

from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent


def main():
    docs = ROOT / "docs"
    outputs = ROOT / "outputs"
    docs.mkdir(exist_ok=True)
    outputs.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
        page.set_default_timeout(30000)
        page.goto("http://127.0.0.1:8521")
        download = page.get_by_text("下载销售日报 Excel", exact=True)
        download.wait_for()
        assert page.get_by_test_id("stException").count() == 0
        page.screenshot(path=str(docs / "sales-daily.png"), full_page=True)
        with page.expect_download() as info:
            download.click()
        info.value.save_as(outputs / "sales_daily_report.xlsx")
        sales = load_workbook(outputs / "sales_daily_report.xlsx")
        assert sales["销售日报"].max_row == 22
        assert "模拟数据" in [r[1].value for r in sales["范围与口径"].iter_rows(min_row=2)]

        page.get_by_test_id("stSidebar").get_by_text("广告报表复盘", exact=True).click()
        page.get_by_text("下载广告复盘 Excel", exact=True).wait_for()
        assert page.get_by_test_id("stException").count() == 0
        page.get_by_role("heading", name="亚马逊运营工作台", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(docs / "ads-review.png"), full_page=True)
        with page.expect_download() as info:
            page.get_by_text("下载广告复盘 Excel", exact=True).click()
        info.value.save_as(outputs / "sp_search_term_review.xlsx")
        ads = load_workbook(outputs / "sp_search_term_review.xlsx")
        assert ads["广告明细"].max_row == 85
        assert ads["复核与行动记录"].max_row == 5

        page.get_by_test_id("stSidebar").get_by_text("销售日报", exact=True).click()
        page.get_by_test_id("stSidebar").get_by_text("导入自己的报表", exact=True).click()
        page.get_by_label("店铺名称", exact=True).fill("DEMO-STORE")
        page.get_by_label("店铺名称", exact=True).press("Enter")
        page.locator('input[type="file"]').set_input_files(ROOT / "examples" / "sales_daily.csv")
        page.get_by_text("下载销售日报 Excel", exact=True).wait_for()
        assert page.get_by_test_id("stException").count() == 0
        with page.expect_download() as info:
            page.get_by_text("下载销售日报 Excel", exact=True).click()
        parsed = load_workbook(BytesIO(info.value.path().read_bytes()))
        assert parsed["销售日报"].max_row == 22

        # Invalid imported amounts must block the result instead of disappearing silently.
        page.close()
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.set_default_timeout(30000)
        page.goto("http://127.0.0.1:8521")
        page.get_by_text("下载销售日报 Excel", exact=True).wait_for()
        page.get_by_test_id("stSidebar").get_by_text("导入自己的报表", exact=True).click()
        page.get_by_label("店铺名称", exact=True).fill("DEMO-STORE")
        page.get_by_label("店铺名称", exact=True).press("Enter")
        content = (ROOT / "examples" / "sales_daily.csv").read_bytes().replace(b"$398.00", b"$-398.00")
        page.locator('input[type="file"]').set_input_files(
            {"name": "invalid.csv", "mimeType": "text/csv", "buffer": content})
        page.get_by_text("本次未生成结果。", exact=False).wait_for()
        assert page.get_by_text("下载销售日报 Excel", exact=True).count() == 0
        assert page.get_by_test_id("stException").count() == 0
        page.get_by_test_id("stSidebar").get_by_text("广告报表复盘", exact=True).click()
        page.get_by_text("上传按日 SP 搜索词报表（可多选，单文件 ≤20 MB）", exact=True).wait_for()
        page.locator('input[type="file"]').set_input_files([
            ROOT / "examples" / "sp_search_terms_old.csv", ROOT / "examples" / "sp_search_terms_updated.csv"])
        try:
            page.get_by_text("下载广告复盘 Excel", exact=True).wait_for()
        except Exception:
            page.screenshot(path=str(outputs / "browser-error.png"), full_page=True)
            print(page.locator("body").inner_text()[-5500:], flush=True)
            raise
        with page.expect_download() as info:
            page.get_by_text("下载广告复盘 Excel", exact=True).click()
        parsed = load_workbook(BytesIO(info.value.path().read_bytes()))
        assert parsed["广告明细"].max_row == 85
        assert page.get_by_test_id("stException").count() == 0
        browser.close()
    print("Browser checks passed: demo modules, Excel downloads, sales/ads CSV uploads, invalid input rejection.")


if __name__ == "__main__":
    main()
