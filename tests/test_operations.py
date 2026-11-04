from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from operations import (
    ReportError,
    Scope,
    ads_report,
    combine,
    excel_bytes,
    normalize,
    number,
    read_table,
    sales_brief,
    sales_report,
    suggest_mapping,
)

ROOT = Path(__file__).resolve().parents[1]
SCOPE = Scope("DEMO-STORE", "US", "USD", "America/Los_Angeles", 7)


def load(name, kind):
    frame = read_table(name, (ROOT / "examples" / name).read_bytes())
    return normalize(frame, kind, suggest_mapping(frame.columns, kind), SCOPE, name)


def test_ad_snapshot_replaces_entire_day_not_just_matching_rows():
    old = load("sp_search_terms_old.csv", "ads")
    new = load("sp_search_terms_updated.csv", "ads")
    day = new["date"].min()
    new = new.loc[~(new["date"].eq(day) & new["search_term"].eq("free organizer"))]
    merged, log = combine([old, new], "ads")
    assert not ((merged["date"] == day) & merged["search_term"].eq("free organizer")).any()
    assert len(merged) == 83
    assert log.iloc[1]["覆盖旧日期行数"] == 20
    assert merged.loc[(merged["date"] == day) & merged["search_term"].eq("desk organizer"), "ad_orders"].iloc[0] == 4


def test_repeat_import_is_idempotent():
    data = load("sp_search_terms_old.csv", "ads")
    once, _ = combine([data], "ads")
    twice, _ = combine([data, data], "ads")
    pd.testing.assert_frame_equal(once, twice)


def test_conflicting_business_key_is_rejected():
    data = load("sp_search_terms_old.csv", "ads")
    conflict = data.iloc[[0]].copy()
    conflict["spend"] = 999
    with pytest.raises(ReportError, match="同一业务键"):
        combine([pd.concat([data, conflict])], "ads")


def test_exact_duplicate_logged():
    data = load("sales_daily.csv", "sales")
    merged, log = combine([pd.concat([data, data.iloc[[0]]])], "sales")
    assert len(merged) == 21
    assert log.iloc[0]["文件内完全重复行"] == 1


def test_calendar_comparison_does_not_skip_missing_days_or_use_zero_base():
    data = load("sales_daily.csv", "sales")
    data = data.loc[~data["date"].eq(pd.Timestamp("2026-10-13"))].copy()
    data.loc[data["date"].eq(pd.Timestamp("2026-10-12")), "sales"] = 0
    report = sales_report(data).set_index("date")
    assert pd.isna(report.loc["2026-10-14", "sales_dod"])
    assert pd.isna(report.loc["2026-10-19", "sales_wow"])
    assert pd.isna(report.loc["2026-10-20", "sales_wow"])


def test_sales_without_sessions_does_not_invent_conversion():
    data = load("sales_daily.csv", "sales").drop(columns=["sessions", "page_views"])
    report = sales_report(data)
    assert "unit_session_rate" not in report
    assert "会话数" not in sales_brief(report, date(2026, 11, 1), SCOPE)


def test_missing_optional_dimension_across_files_is_rejected():
    data = load("sales_daily.csv", "sales")
    with pytest.raises(ReportError, match="字段不一致"):
        combine([data, data.drop(columns="sessions")], "sales")


def test_weighted_ratios_not_average_of_rates():
    data = load("sp_search_terms_old.csv", "ads").iloc[[0, 4]].copy()
    data["spend"] = [10, 20]
    data["ad_sales"] = [20, 100]
    data["clicks"] = [10, 100]
    _, summary, _ = ads_report(data, SCOPE, date(2026, 11, 3))
    assert summary.iloc[0]["acos"] == pytest.approx(30 / 120)
    assert summary.iloc[0]["cpc"] == pytest.approx(30 / 110)
    assert summary.iloc[0]["acos"] != pytest.approx((0.5 + 0.2) / 2)


def test_recent_days_are_visible_but_excluded_from_action_candidates():
    data = load("sp_search_terms_updated.csv", "ads")
    detailed, summary, review = ads_report(data, SCOPE, date(2026, 11, 3))
    assert detailed.loc[detailed["date"].eq(pd.Timestamp("2026-10-27")), "mature"].eq(False).all()
    assert summary["spend"].sum() == pytest.approx(data["spend"].sum())
    assert review["spend"].sum() == pytest.approx(detailed.loc[detailed["mature"], "spend"].sum())
    pending = data.loc[data["date"].ge(pd.Timestamp("2026-10-27"))]
    _, _, empty = ads_report(pending, SCOPE, date(2026, 11, 3))
    assert empty.empty


def test_rules_only_select_sufficient_mature_samples():
    data = load("sp_search_terms_old.csv", "ads")
    _, _, review = ads_report(data, SCOPE, date(2026, 11, 3), target_acos=0.3)
    row = review.loc[review["search_term"].eq("free organizer")].iloc[0]
    assert row["status"] == "待复核"
    assert pd.isna(row["acos"])
    assert "人工" in row["action"]


def test_future_data_rejected():
    with pytest.raises(ReportError, match="晚于"):
        ads_report(load("sp_search_terms_old.csv", "ads"), SCOPE, date(2026, 10, 1))


@pytest.mark.parametrize("value", ["", "-", "NaN", "-1", "1.234,56", "1,23", "∞", "EUR 10", "£10"])
def test_bad_numbers_rejected(value):
    with pytest.raises(ReportError):
        number(value, "USD")


def test_money_parsing():
    assert number("USD 1,234.56", "USD") == 1234.56
    assert number("$0.00", "USD") == 0


def test_multi_date_aggregate_rejected():
    raw = pd.DataFrame({"Start Date": ["2026-10-01"], "End Date": ["2026-10-31"],
                        "Ordered Product Sales": [100], "Units Ordered": [5], "Total Order Items": [4]})
    with pytest.raises(ReportError, match="跨日期汇总"):
        normalize(raw, "sales", suggest_mapping(raw.columns, "sales"), SCOPE, "aggregate.csv")


def test_scope_conflict_rejected():
    raw = read_table("sales_daily.csv", (ROOT / "examples" / "sales_daily.csv").read_bytes())
    raw.loc[0, "Currency"] = "EUR"
    with pytest.raises(ReportError, match="范围不一致"):
        normalize(raw, "sales", suggest_mapping(raw.columns, "sales"), SCOPE, "mixed.csv")


def test_wrong_window_and_same_sku_manual_mapping_rejected():
    raw = read_table("sp.csv", (ROOT / "examples" / "sp_search_terms_old.csv").read_bytes())
    raw["14 Day Total Sales"] = raw["7 Day Total Sales"]
    raw["7 Day Advertised SKU Sales"] = raw["7 Day Total Sales"]
    mapping = suggest_mapping(raw.columns, "ads")
    for field in ("14 Day Total Sales", "7 Day Advertised SKU Sales"):
        with pytest.raises(ReportError):
            normalize(raw, "ads", {**mapping, "ad_sales": field}, SCOPE, "wrong.csv")


def test_xlsx_export_reopens_and_preserves_text_without_formulas():
    tables = {"复盘": pd.DataFrame({"search_term": ["=HYPERLINK(\"https://example.com\")", "+SUM(1,2)"],
                                   "acos": [0.25, float("nan")]})}
    content = excel_bytes(tables, [("店铺", "DEMO")])
    book = load_workbook(BytesIO(content), data_only=False)
    assert book["复盘"]["A2"].value.startswith("=")
    assert book["复盘"]["A2"].data_type == "s"
    assert book["复盘"]["B2"].number_format == "0.00%"
    assert book["复盘"]["B3"].value is None
    assert all(c.data_type != "f" for sheet in book for row in sheet for c in row)


def test_csv_encoding_and_xlsx_round_trip():
    data = pd.DataFrame({"日期": ["2026-11-01"], "标题": ["中文"]})
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        parsed = read_table("test.csv", data.to_csv(index=False).encode(encoding))
        assert parsed.iloc[0]["标题"] == "中文"
    content = BytesIO()
    data.to_excel(content, index=False)
    assert read_table("test.xlsx", content.getvalue()).iloc[0]["标题"] == "中文"


def test_missing_required_mapping_rejected():
    with pytest.raises(ReportError, match="缺少映射"):
        normalize(pd.DataFrame({"Date": ["2026-11-01"]}), "sales", {"date": "Date"}, SCOPE, "bad.csv")
