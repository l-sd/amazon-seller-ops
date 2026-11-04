"""Patch explicit daily values in an existing OOXML workbook without re-saving unrelated parts."""

import hashlib
import io
import re
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from html import escape
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
from openpyxl.utils.datetime import from_excel

from operations import ReportError, number, read_table
from rank_reports import consolidate, load_observations

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", NS)


def normalized_word(value):
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def iso_day(value):
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, (int, float)):
        return from_excel(value).date().isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return None


def _numeric(value, currency):
    if pd.isna(value) or str(value).strip() == "":
        return None
    return number(value, currency)


def _read(path):
    return read_table(path.name, path.read_bytes()).fillna("")


def prepare_daily(profile, target_day, inputs):
    """Only normalized records with explicit scope; unknowns remain blank."""
    date.fromisoformat(target_day)
    required = ["store", "marketplace", "currency", "parent_asin", "children", "rank_asin", "rank_provider", "timezone"]
    if any(not profile.get(k) for k in required):
        raise ReportError("配置缺店铺、站点、币种、父子 ASIN、排名 ASIN/工具或时区。")
    if profile.get("rank_type", "organic") != "organic":
        raise ReportError("当前总表配置已确认为自然排名；广告排名应使用独立列和配置。")
    children = set(profile["children"])
    if profile["rank_asin"] not in children:
        raise ReportError("排名 ASIN 必须是已确认的具体子体。")
    warnings, lineage, values, keyword_values = [], [], {}, {}

    def records(kind):
        if kind not in inputs:
            warnings.append(f"未提供{kind}资料，此模块未更新")
            return None
        path = inputs[kind]
        raw = _read(path)
        necessary = {"date", "store", "marketplace", "currency", "child_asin"}
        if not necessary.issubset(raw):
            raise ReportError(f"{kind} 缺少范围或日期/子 ASIN 字段。")
        for col in ("store", "marketplace", "currency"):
            if set(raw[col].astype(str).str.strip()) != {profile[col]}:
                raise ReportError(f"{kind} 的 {col} 与总表范围不同，拒绝混合。")
        if any(iso_day(v) is None for v in raw["date"]):
            raise ReportError(f"{kind} 含非 ISO 日期，先标准化，不猜测月日顺序。")
        raw["date"] = raw["date"].map(iso_day)
        raw = raw.loc[raw["date"].eq(target_day)].copy()
        if raw.empty:
            warnings.append(f"{kind} 没有目标日期，未更新对应数据")
            return None
        if not set(raw["child_asin"]).issubset(children):
            raise ReportError(f"{kind} 包含未确认归属本父体的子 ASIN。")
        if "parent_asin" in raw and set(raw["parent_asin"]) != {profile["parent_asin"]}:
            raise ReportError(f"{kind} 父 ASIN 对照不一致。")
        lineage.append({"kind": kind, "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "date": target_day, "rows": len(raw)})
        return raw

    business = records("business")
    if business is not None:
        cols = ["sales", "order_items", "units", "sessions"]
        if not set(cols).issubset(business):
            raise ReportError("业务表缺销售额、订单项、件数或会话字段。")
        business = business.drop_duplicates()
        if business.duplicated(["date", "child_asin"]).any():
            raise ReportError("同一子体同一天有不同业务数据，需核对快照，不能相加。")
        if set(business["child_asin"]) != children:
            warnings.append("业务表缺少已配置子体，未把部分数据写成父体总计")
        else:
            for col in cols:
                converted = business[col].map(lambda v: _numeric(v, profile["currency"]))
                if converted.isna().any():
                    warnings.append(f"业务 {col} 有缺失，未更新该字段")
                else:
                    values[col] = float(converted.sum())
            # Units/sessions is explicit; never derive organic traffic by subtracting clicks.
            if values.get("sessions", 0) > 0 and "units" in values:
                values["unit_session_rate"] = values["units"] / values["sessions"]
    ads = records("ads")
    if ads is not None:
        required_ads = {"campaign", "ad_group", "report_kind", "attribution_window", "impressions", "clicks",
                        "spend", "ad_sales", "ad_orders", "ad_units"}
        if not required_ads.issubset(ads):
            raise ReportError("广告资料缺少完整商品推广报表字段/归因窗口。")
        if set(ads["report_kind"]) != {"advertised_product"}:
            raise ReportError("总表广告总计使用 advertised_product 报表，不能用搜索词样本代替。")
        if set(ads["attribution_window"].astype(str)) != {str(profile.get("attribution_window", 7))}:
            raise ReportError("广告归因窗口不同，不能混算。")
        ads = ads.drop_duplicates()
        if ads.duplicated(["date", "child_asin", "campaign", "ad_group"]).any():
            raise ReportError("广告同一业务键有冲突记录，先核对报表粒度。")
        if not profile.get("ads_complete", False):
            warnings.append("尚未确认广告导出范围完整，未写入父体广告总计")
        else:
            for col in ("impressions", "clicks", "spend", "ad_sales", "ad_orders", "ad_units"):
                nums = ads[col].map(lambda v: _numeric(v, profile["currency"]))
                if nums.isna().any():
                    warnings.append(f"广告 {col} 有缺失，未更新该字段")
                else:
                    values[col] = float(nums.sum())
            for key, numerator, denominator in (("cpc", "spend", "clicks"), ("acos", "spend", "ad_sales"),
                    ("ad_order_rate", "ad_orders", "clicks"), ("cpa", "spend", "ad_orders"), ("ctr", "clicks", "impressions")):
                if numerator in values and values.get(denominator, 0) > 0:
                    values[key] = values[numerator] / values[denominator]
            warnings.append("广告为点击归因口径，近期结果可能更新；不与订购口径相减来计算自然订单")
    pages = records("pages")
    if pages is not None:
        if pages.duplicated(["date", "child_asin"]).any():
            raise ReportError("同一子体有多条页面快照，先确认当日采样规则。")
        for column, spec in profile.get("page_columns", {}).items():
            row = pages.loc[pages["child_asin"].eq(spec["asin"])]
            field = spec["field"]
            if len(row) != 1 or field not in row:
                warnings.append(f"页面字段 {field} 未提供或子体不匹配")
            else:
                value = _numeric(row.iloc[0][field], profile["currency"])
                if value is not None:
                    values[f"column:{column}"] = value
    if "ranks" in inputs:
        rows, source = load_observations(inputs["ranks"], profile["data_kind"], {})
        _, daily = consolidate(rows)
        match = daily.loc[daily["date"].eq(target_day) & daily["asin"].eq(profile["rank_asin"]) &
                          daily["rank_type"].eq("organic") & daily["rank_definition"].eq("absolute") &
                          daily["provider"].eq(profile["rank_provider"]) & daily["marketplace"].eq(profile["marketplace"]) &
                          daily["timezone"].eq(profile["timezone"])]
        if profile.get("delivery_region"):
            match = match.loc[match["delivery_region"].eq(profile["delivery_region"])]
        if profile.get("device"):
            match = match.loc[match["device"].eq(profile["device"])]
        if match.duplicated("keyword").any():
            raise ReportError("同词存在不同采样/设备/地区口径，不能写入同一个总表列。")
        for row in match.to_dict(orient="records"):
            value = int(row["rank"]) if row["status"] == "found" else {
                "not_collected": "未采集", "unavailable": "采集失败", "out_of_range": f"超出采集范围（{int(row['search_limit'])}）"}[row["status"]]
            keyword_values[row["keyword"]] = value
        lineage.append({"kind": "ranks", **source, "matched_rows": len(match)})
        if not len(match):
            warnings.append("排名表无符合目标日期和自然位范围的记录，关键词列留空")
    else:
        warnings.append("未提供排名表，关键词列未更新")
    return values, keyword_values, warnings, lineage


def patch_ooxml(content, sheet_name, patches):
    """Copy every unrelated ZIP member byte-for-byte, including WPS/VML extensions."""
    source = ZipFile(io.BytesIO(content))
    workbook = ET.fromstring(source.read("xl/workbook.xml"))
    rels = ET.fromstring(source.read("xl/_rels/workbook.xml.rels"))
    relationship = next(n.get(f"{{{REL}}}id") for n in workbook.findall(f"{{{NS}}}sheets/{{{NS}}}sheet") if n.get("name") == sheet_name)
    target = next(n.get("Target") for n in rels if n.get("Id") == relationship)
    member = target.lstrip("/") if target.startswith("/") else "xl/" + target
    xml = source.read(member).decode("utf-8")
    if "<sheetData" not in xml:
        raise ReportError("该工作表使用尚未适配的 XML 前缀，未修改。")
    for coordinate, value in patches.items():
        rownum = int(re.search(r"\d+$", coordinate).group())
        colnum = column_index_from_string(re.match(r"[A-Z]+", coordinate).group())
        row_pattern = r'<row\b(?=[^>]*\br="' + str(rownum) + r'")[^>]*?(?:/>|>.*?</row>)'
        row_match = re.search(row_pattern, xml, re.S)
        if row_match is None:
            next_row = next((m for m in re.finditer(r'<row\b[^>]*\br="(\d+)"', xml) if int(m.group(1)) > rownum), None)
            position = next_row.start() if next_row else xml.index("</sheetData>")
            row_text = f'<row r="{rownum}"></row>'
            xml = xml[:position] + row_text + xml[position:]
            row_match = re.search(row_pattern, xml, re.S)
        row_text = row_match.group()
        if row_text.endswith("/>"):
            row_text = row_text[:-2] + "></row>"
        cell_pattern = r'<c\b(?=[^>]*\br="' + coordinate + r'")[^>]*?(?:/>|>.*?</c>)'
        cell_match = re.search(cell_pattern, row_text, re.S)
        attrs = re.match(r'<c\b([^>]*?)(?:/?>)', cell_match.group()).group(1).rstrip("/") if cell_match else f' r="{coordinate}"'
        attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
        if isinstance(value, (int, float, Decimal)):
            cell_xml = f'<c{attrs}><v>{value}</v></c>'
        else:
            cell_xml = f'<c{attrs} t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
        if cell_match:
            row_text = row_text[:cell_match.start()] + cell_xml + row_text[cell_match.end():]
        else:
            following = next((m for m in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"', row_text)
                              if column_index_from_string(m.group(1)) > colnum), None)
            position = following.start() if following else row_text.index("</row>")
            row_text = row_text[:position] + cell_xml + row_text[position:]
        xml = xml[:row_match.start()] + row_text + xml[row_match.end():]
    # Validate while retaining untouched namespace declarations, extensions and cached formulas.
    ET.fromstring(xml)
    output = io.BytesIO()
    with ZipFile(output, "w") as destination:
        for item in source.infolist():
            destination.writestr(deepcopy(item), xml.encode("utf-8")
                                 if item.filename == member else source.read(item.filename))
    return output.getvalue(), member


def update_master(template, output, profile, target_day, inputs):
    if template.resolve() == output.resolve() or output.exists():
        raise ReportError("只允许生成新副本，不能覆盖原表或已有输出。")
    raw = template.read_bytes()
    book = load_workbook(io.BytesIO(raw), data_only=False)
    sheet = book[profile.get("sheet", "运营总表")]
    header_row = profile.get("header_row", 8)
    start = profile.get("first_data_row", 10)
    date_col = profile.get("date_column", "A")
    values, ranks, warnings, lineage = prepare_daily(profile, target_day, inputs)
    if not values and not ranks:
        raise ReportError("没有可用的目标日数据，未创建空白日期记录。")
    field_columns = profile["field_columns"]
    for field, expected in (("order_items", "订单项"), ("sessions", "会话"), ("unit_session_rate", "件数")):
        if field in field_columns:
            header = str(sheet[f"{field_columns[field]}{header_row}"].value or "")
            if expected not in header:
                warnings.append(f"列 {field_columns[field]} 原表头“{header}”与标准字段 {field} 不完全一致；需按审计口径阅读，未擅自改表头")
    allowed = {"sales", "order_items", "units", "sessions", "unit_session_rate", "impressions", "clicks",
               "spend", "ad_sales", "ad_orders", "ad_units", "cpc", "acos", "ad_order_rate", "cpa", "ctr"}
    if set(field_columns) - allowed:
        raise ReportError("总表字段含未支持或未经确认的推算口径。")
    banned = {"organic_traffic", "organic_orders", "organic_conversion", "total_sessions_plus_clicks"}
    if banned & set(field_columns):
        raise ReportError("禁止沿用会话+点击或总订单-广告归因订单作为自然数据。")
    dates = [r for r in range(start, sheet.max_row + 1) if iso_day(sheet[f"{date_col}{r}"].value) == target_day]
    if len(dates) > 1:
        raise ReportError("总表已有多个同日行，需先核对重复记录。")
    if dates:
        target_row = dates[0]
    else:
        # Existing content or formulas count as occupied, including rows with an empty date cell.
        target_row = next((r for r in range(start, sheet.max_row + 2)
                           if all(sheet.cell(r, c).value is None for c in range(1, sheet.max_column + 1))), None)
        if target_row is None:
            raise ReportError("没有安全空白行，未写入。")
    patches, changes = {}, []

    def add(column, value, source):
        if value is None:
            return
        if not re.fullmatch(r"[A-Z]+", column) or column in profile.get("manual_columns", ["AI", "AJ", "AK"]):
            raise ReportError("目标列无效或属于人工分析/日志区。")
        coordinate = f"{column}{target_row}"
        current = sheet[coordinate]
        if current.data_type == "f":
            warnings.append(f"{coordinate} 是已有公式，保留未覆盖")
            return
        if current.value is not None and current.value != value:
            if column == date_col and iso_day(current.value) == target_day:
                return
            raise ReportError(f"{coordinate} 已有不同数据，未覆盖；需明确同日更正策略。")
        if current.value is None:
            patches[coordinate] = value
            changes.append({"cell": coordinate, "value": value, "source": source})

    add(date_col, target_day, "明确目标日期")
    for field, column in field_columns.items():
        if field in values:
            add(column, values[field], field)
    for field, value in values.items():
        if field.startswith("column:"):
            add(field.split(":", 1)[1], value, "页面快照")
    first_keyword = column_index_from_string(profile.get("keyword_start_column", "AM"))
    keyword_headers = {}
    for column in range(first_keyword, sheet.max_column + 1):
        cell = sheet.cell(header_row, column)
        if cell.value is not None:
            word = normalized_word(cell.value)
            if word in keyword_headers:
                raise ReportError("总表关键词表头重复，无法安全匹配。")
            keyword_headers[word] = cell.column_letter
    for word, column in keyword_headers.items():
        if word in ranks:
            add(column, ranks[word], "自然排名导出")
        else:
            warnings.append(f"总表关键词 {word} 无本日记录，保留空白而不是填 0")
    unmatched = sorted(set(ranks) - set(keyword_headers))
    errors = [{"sheet": sh.title, "cell": c.coordinate, "formula": c.value} for sh in book for row in sh for c in row
              if c.data_type == "f" and "#REF!" in c.value]
    if errors:
        warnings.append(f"原模板已有 {len(errors)} 个含 #REF! 的公式，未擅自修复或删除")
    patched, member = patch_ooxml(raw, sheet.title, patches)
    reread = load_workbook(io.BytesIO(patched), data_only=False)
    for coordinate, expected in patches.items():
        actual = reread[sheet.title][coordinate].value
        if isinstance(expected, (int, float)):
            if abs(actual - expected) > 0.00000001:
                raise ReportError("写入后数值回读不一致。")
        elif actual != expected:
            raise ReportError("写入后文本回读不一致。")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(patched)
    return {"template_sha256": hashlib.sha256(raw).hexdigest(), "output": output.name, "date": target_day,
            "sheet": sheet.title, "row": target_row, "changes": changes, "warnings": warnings,
            "unmatched_rank_words": unmatched, "preexisting_ref_errors": errors, "sources": lineage,
            "only_modified_package_part": member, "manual_analysis_and_logs": "preserved; not auto-filled",
            "data_kind": profile["data_kind"]}
