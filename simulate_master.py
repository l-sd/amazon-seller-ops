"""Simulate external exports and three daily master updates; never publish a supplied template."""

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from master_workbook import update_master

CHILDREN = ["B0DEMO0001", "B0DEMO0002"]
FIELDS = {"sales": "N", "order_items": "O", "units": "P", "sessions": "Q", "unit_session_rate": "R",
          "clicks": "V", "spend": "W", "cpc": "X", "ad_orders": "Y", "ad_units": "Z", "ad_sales": "AA",
          "ad_order_rate": "AB", "acos": "AC", "cpa": "AF", "impressions": "AG", "ctr": "AH"}


def create_clean_template(path):
    book = Workbook()
    sheet = book.active
    sheet.title = "运营总表"
    sheet["A1"] = "模拟总表 · 非用户原模板"
    sheet["A8"] = "美国日期"
    labels = {"B": "演示变体 A 价格", "C": "演示变体 B 价格", "N": "订购销售额", "O": "订单项数", "P": "订购件数", "Q": "会话数", "R": "订购件数/会话数",
              "V": "广告点击", "W": "广告花费", "X": "CPC", "Y": "归因订单", "Z": "归因件数", "AA": "归因销售额",
              "AB": "归因订单/点击", "AC": "ACOS", "AF": "CPA", "AG": "广告曝光", "AH": "CTR", "AK": "人工操作记录",
              "AM": "desk organizer", "AN": "small desk organizer", "AO": "desktop storage"}
    for column, label in labels.items():
        sheet[f"{column}8"] = label
    for row in range(8, 20):
        for col in range(1, 42):
            cell = sheet.cell(row, col)
            cell.fill = PatternFill("solid", fgColor="173C55" if row == 8 else ("EEF4F1" if row % 2 else "FFFFFF"))
            cell.font = Font(name="Microsoft YaHei", size=10, color="FFFFFF" if row == 8 else "173C55")
    sheet["AF10"] = '=IFERROR(X10/AB10,"")'
    sheet.freeze_panes = "B9"
    sheet.sheet_view.showGridLines = False
    for col in range(1, 42):
        letter = sheet.cell(8, col).column_letter
        sheet.column_dimensions[letter].width = 25 if letter not in ("AM", "AN", "AO") else 30
        if letter != "A" and letter not in labels:
            sheet.column_dimensions[letter].hidden = True
        for row in range(9, 20):
            if letter in ("R", "AB", "AC", "AH"):
                sheet.cell(row, col).number_format = "0.0%"
            elif letter in ("B", "C", "N", "W", "X", "AA", "AF"):
                sheet.cell(row, col).number_format = '$#,##0.00'
    sheet["AK15"] = "人工日志占位，不能覆盖"
    book.create_sheet("后台业务报告（子）")["A1"] = "模拟结构；原始导出保存在独立文件"
    book.create_sheet("后台广告报告")["A1"] = "模拟结构"
    book.save(path)


def run_simulation(destination, template=None):
    destination.mkdir(parents=True, exist_ok=False)
    if template is None:
        template = destination / "synthetic_template.xlsx"
        create_clean_template(template)
    original_hash = hashlib.sha256(template.read_bytes()).hexdigest()
    sheet = load_workbook(template)["运营总表"]
    keywords = [str(sheet.cell(8, col).value) for col in range(39, sheet.max_column + 1) if sheet.cell(8, col).value is not None]
    profile = {"sheet": "运营总表", "header_row": 8, "first_data_row": 10, "date_column": "A", "store": "DEMO-STORE",
               "marketplace": "US", "currency": "USD", "parent_asin": "B0DEMOP001", "children": CHILDREN,
               "rank_asin": CHILDREN[0], "rank_provider": "DEMO-EXPORT", "rank_type": "organic",
               "timezone": "America/Los_Angeles", "delivery_region": "US-10001", "device": "desktop",
               "data_kind": "synthetic", "ads_complete": True, "attribution_window": 7, "field_columns": FIELDS,
               "page_columns": {"B": {"asin": CHILDREN[0], "field": "price"}, "C": {"asin": CHILDREN[1], "field": "price"}}}
    (destination / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    business, ads, pages, ranks = [], [], [], []
    for day_index in range(3):
        day = (date(2026, 11, 1) + timedelta(days=day_index)).isoformat()
        for i, child in enumerate(CHILDREN):
            common = {"date": day, "store": "DEMO-STORE", "marketplace": "US", "currency": "USD", "child_asin": child}
            business.append({**common, "parent_asin": profile["parent_asin"], "sales": 150 + i * 50 + day_index * 20,
                             "order_items": 10 + i, "units": 12 + i * 2, "sessions": 100 + i * 50})
            ads.append({**common, "campaign": f"DEMO-{i}", "ad_group": "DEMO", "report_kind": "advertised_product",
                        "attribution_window": 7, "impressions": 1000 + i * 500, "clicks": 20 + i * 10, "spend": 10 + i * 5,
                        "ad_sales": 60 + i * 20, "ad_orders": 4 + i, "ad_units": 5 + i})
            pages.append({**common, "price": 19.9 + i})
        for j, keyword in enumerate(keywords):
            missing = j == len(keywords) - 1 and day_index == 2
            ranks.append({"provider": "DEMO-EXPORT", "marketplace": "US", "asin": CHILDREN[0], "keyword": keyword,
                          "rank_type": "organic", "rank_definition": "absolute", "device": "desktop",
                          "delivery_region": "US-10001", "sampling_rule": "daily_latest", "timezone": "America/Los_Angeles",
                          "observed_at": f"{day}T10:00:00-08:00", "rank": "" if missing else 90 - day_index * 3 + j * 2,
                          "status": "not_collected" if missing else "found", "search_limit": 306,
                          "source_reference": "synthetic://external-rank-table", "data_kind": "synthetic"})
    inputs = {}
    for name, records in (("business", business), ("ads", ads), ("pages", pages), ("ranks", ranks)):
        path = destination / f"{name}.csv"
        pd.DataFrame(records).to_csv(path, index=False, encoding="utf-8-sig")
        inputs[name] = path
    current = template
    audits = []
    for day_index in range(3):
        day = (date(2026, 11, 1) + timedelta(days=day_index)).isoformat()
        output = destination / f"master-synthetic-{day}.xlsx"
        audit = update_master(current, output, profile, day, inputs)
        audits.append(audit)
        current = output
    book = load_workbook(current)
    target = book["运营总表"]
    for audit in audits:
        r = audit["row"]
        assert target[f"Q{r}"].value == 250  # Sessions, never 250 + 50 ad clicks.
        assert target[f"V{r}"].value == 50
        assert target[f"O{r}"].value == 21
        assert target[f"P{r}"].value == 26
        assert target[f"S{r}"].value is None and target[f"T{r}"].value is None
    original, updated = ZipFile(template), ZipFile(current)
    modified = {audit["only_modified_package_part"] for audit in audits}
    untouched = all(original.read(n) == updated.read(n) for n in original.namelist() if n not in modified)
    assert untouched
    assert hashlib.sha256(template.read_bytes()).hexdigest() == original_hash
    result = {"data_kind": "synthetic", "template_sha256": original_hash, "original_unchanged": True,
              "unrelated_package_parts_unchanged": untouched, "days": audits, "final_workbook": current.name,
              "note": "仅模拟源表和逐日整合，不代表真实网站导出适配或经营数据"}
    (destination / "simulation-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="使用模拟网站/业务/广告/排名导出测试总表维护流程")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, help="可选真实模板，只生成本地测试副本，不能上传该模板或副本")
    args = parser.parse_args()
    result = run_simulation(args.output_dir, args.template)
    print(json.dumps({"status": "ok", "days": len(result["days"]), "final_workbook": result["final_workbook"],
                      "original_unchanged": result["original_unchanged"],
                      "unrelated_parts_preserved": result["unrelated_package_parts_unchanged"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
