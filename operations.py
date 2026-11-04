"""Local report processing. Inputs are immutable; all report scopes are explicit."""

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


class ReportError(ValueError):
    """An actionable input error suitable for showing in the UI."""


@dataclass(frozen=True)
class Scope:
    store: str
    marketplace: str
    currency: str
    timezone: str
    window: int = 7

    def validate(self):
        if not all(x.strip() for x in (self.store, self.marketplace, self.currency, self.timezone)):
            raise ReportError("请填写店铺、站点、币种和报表时区。")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ReportError("币种请使用三个大写字母，例如 USD。")
        if self.window not in (7, 14):
            raise ReportError("第一版支持 7 天或 14 天的点击归因窗口。")


BASE = {"date": ["Date", "日期", "Start Date", "开始日期"]}
SALES = {
    **BASE,
    "sales": ["Ordered Product Sales", "已订购商品销售额", "订购商品销售额"],
    "units": ["Units Ordered", "已订购商品数量", "订购商品数量"],
    "order_items": ["Total Order Items", "订单商品总数", "订单项总数"],
    "sessions": ["Sessions - Total", "Sessions – Total", "Sessions", "会话数", "会话数 - 总计"],
    "page_views": ["Page Views - Total", "Page Views – Total", "Page Views", "页面浏览量"],
}
ADS = {
    **BASE,
    "campaign": ["Campaign Name", "广告活动名称"],
    "ad_group": ["Ad Group Name", "广告组名称"],
    "targeting": ["Targeting", "投放", "Keyword", "关键词"],
    "match_type": ["Match Type", "匹配类型"],
    "search_term": ["Customer Search Term", "客户搜索词"],
    "impressions": ["Impressions", "展示量", "曝光量"],
    "clicks": ["Clicks", "点击量", "点击次数"],
    "spend": ["Spend", "花费", "支出"],
}
LABELS = {
    "date": "日期", "sales": "订购商品销售额", "units": "订购件数", "order_items": "订单项数",
    "sessions": "会话数", "page_views": "页面浏览量", "campaign": "广告活动", "ad_group": "广告组",
    "targeting": "投放词或目标", "match_type": "匹配类型", "search_term": "客户搜索词",
    "impressions": "搜索词报表曝光量", "clicks": "点击量", "spend": "广告花费",
    "ad_sales": "归因销售额", "ad_orders": "归因订单数", "ctr": "点击率", "cpc": "平均点击成本",
    "acos": "ACOS", "roas": "ROAS", "ad_order_rate": "归因订单数/点击量",
    "unit_session_rate": "订购件数/会话数", "sales_dod": "销售额较前一日", "sales_wow": "销售额较上周同日",
    "source": "来源文件", "status": "复核状态", "reason": "触发原因", "action": "建议复核方向",
    "review_note": "人工处理备注", "mature": "所选截止日归因已完整等待", "age": "距所选截止日天数",
}
NOTES = [
    "销售日报是按日期的订购商品销售额、订购件数及订单项数；不等于结算收入、净销售额或独立订单数。",
    "会话数缺失时不计算订购件数/会话数；该比率不是买家转化率，可能超过 100%。",
    "前一日/上周同日必须有对应自然日记录且分母非零；不跨缺失日期比较，不自动填零。",
    "广告仅覆盖导入的 SP 搜索词报表，不代表全部广告曝光；搜索词可能是文字或 ASIN。",
    "归因销售额须使用同一窗口的总归因销售额，不混入同 SKU 销售额或不同归因窗口。",
    "近期数据仍可能更新。完整等待标记仅依据报告日期和所选截止日，不证明平台已最终结算。",
    "比率为汇总分子除以汇总分母；零分母为空；不计算利润、TACOS 或自动执行投放调整。",
    "同一批仅限同店铺、同站点、同币种、同报表时区；时间窗口不同的数据不能混入。",
    "多个文件按界面顺序由旧到新。后一个文件覆盖已有日期的整个分区，包括该日旧快照中已消失的搜索词。",
    "所有异常均为人工复核候选，阈值由用户设置，不是平台规则或确定的经营原因。",
]


def aliases(kind, window=7):
    result = dict(SALES if kind == "sales" else ADS)
    if kind == "ads":
        result["ad_sales"] = [f"{window} Day Total Sales", f"{window} Day Total Sales ($)",
                              f"{window}天总销售额", f"{window}天总销售额 ($)"]
        result["ad_orders"] = [f"{window} Day Total Orders (#)", f"{window} Day Total Orders",
                               f"{window}天总订单数", f"{window}天总订单数 (#)"]
    return result


def token(value):
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def suggest_mapping(columns, kind, window=7):
    """Return unambiguous aliases only; attribution fields stay window-specific."""
    result = {}
    for key, names in aliases(kind, window).items():
        matches = [c for c in columns if token(c) in {token(key), *(token(n) for n in names)}]
        if len(matches) == 1:
            result[key] = matches[0]
    return result


def read_table(name, content):
    if len(content) > 20 * 1024 * 1024:
        raise ReportError(f"{name} 超过 20 MB，请分批导出。")
    if name.lower().endswith(".xlsx"):
        try:
            book = pd.ExcelFile(BytesIO(content), engine="openpyxl")
            if len(book.sheet_names) != 1:
                raise ReportError("请提供只含一张数据表的 XLSX，或另存为 CSV。")
            frame = pd.read_excel(book, dtype=str)
        except ReportError:
            raise
        except Exception as exc:
            raise ReportError(f"无法打开 {name}，请检查文件是否完整。") from exc
    elif name.lower().endswith((".csv", ".tsv")):
        frame = None
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            try:
                frame = pd.read_csv(BytesIO(content), encoding=encoding, sep=None, engine="python", dtype=str)
                break
            except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
                continue
        if frame is None:
            raise ReportError(f"无法识别 {name}，请另存为 CSV UTF-8。")
    else:
        raise ReportError("只支持 CSV、TSV 和 XLSX。")
    if frame.empty:
        raise ReportError(f"{name} 没有数据行。")
    frame.columns = [str(c).strip() for c in frame.columns]
    if frame.columns.duplicated().any():
        raise ReportError(f"{name} 含有重名列。")
    return frame


def parse_dates(series):
    def parse(value):
        raw = str(value).strip()
        # Ambiguous 03/04/2026 is never guessed. US aliases accept M/D/YYYY explicitly.
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                return pd.to_datetime(raw, format=fmt).normalize()
            except (ValueError, TypeError):
                pass
        raise ReportError(f"日期无法识别：{raw}。支持 YYYY-MM-DD、YYYY/MM/DD 或美式 MM/DD/YYYY。")
    return series.map(parse)


def number(value, currency):
    raw = str(value).strip().replace("\u00a0", " ")
    if raw.lower() in ("", "nan", "none", "-", "n/a"):
        raise ReportError("数值字段存在空白或占位符；请核对原始报表，不能自动当成 0。")
    codes = re.findall(r"[A-Za-z]{3}", raw)
    if codes and any(c.upper() != currency for c in codes):
        raise ReportError(f"数值币种与所选 {currency} 不一致：{raw}")
    for symbol, allowed in (("$", {"USD", "CAD", "AUD", "SGD", "MXN"}), ("€", {"EUR"}),
                            ("£", {"GBP"}), ("¥", {"JPY", "CNY"})):
        if symbol in raw and currency not in allowed:
            raise ReportError(f"金额符号与所选 {currency} 不一致：{raw}")
    raw = re.sub(r"[A-Za-z]{3}", "", raw).strip()
    raw = raw.lstrip("$€£¥").strip()
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", raw):
        raise ReportError(f"数值格式无法识别：{value}。第一版使用小数点、逗号千分位；不接受负数。")
    result = float(raw.replace(",", ""))
    if not math.isfinite(result):
        raise ReportError("数值过大或不是有限数。")
    return result


def normalize(frame, kind, mapping, scope, name):
    scope.validate()
    required = set(SALES) - {"sessions", "page_views"} if kind == "sales" else set(aliases("ads", scope.window))
    missing = required - set(mapping)
    if missing:
        raise ReportError(f"{name} 缺少映射：{'、'.join(LABELS[k] for k in sorted(missing))}。请在字段映射中选择。")
    if len(set(mapping.values())) != len(mapping):
        raise ReportError("同一来源列不能映射到两个字段。")
    if any(c not in frame for c in mapping.values()):
        raise ReportError("字段映射指向不存在的列。")
    # Explicit source metadata, when present, must agree with UI declarations.
    for key, expected, names in (
        ("store", scope.store, ["Store", "店铺"]),
        ("marketplace", scope.marketplace, ["Marketplace", "站点"]),
        ("currency", scope.currency, ["Currency", "币种"]),
        ("timezone", scope.timezone, ["Timezone", "时区"]),
    ):
        for c in frame.columns:
            if token(c) in {key, *(token(n) for n in names)}:
                if frame[c].isna().any() or set(frame[c].astype(str).str.strip()) != {expected}:
                    raise ReportError(f"{name} 的 {key} 与所选范围不一致。请分开处理。")
    if kind == "ads":
        for c in frame.columns:
            if token(c) in {"ad product", "广告类型"}:
                if set(frame[c].astype(str).str.upper()) != {"SPONSORED_PRODUCTS"}:
                    raise ReportError("仅支持 SPONSORED_PRODUCTS（SP）搜索词报表。")
        # Reject recognizable wrong-window or same-SKU mappings even when manually chosen.
        for key in ("ad_sales", "ad_orders"):
            source = token(mapping[key])
            if "sku" in source or "promoted" in source:
                raise ReportError("请选择总归因销售/订单列，不能使用同 SKU 或 promoted 列。")
            windows = re.findall(r"(7|14|30|1)\s*(?:day|天|d\b)", source)
            if windows and any(int(w) != scope.window for w in windows):
                raise ReportError("映射列的归因窗口与所选窗口不一致。")
    data = frame[list(mapping.values())].rename(columns={v: k for k, v in mapping.items()}).copy()
    data["date"] = parse_dates(data["date"])
    for c in frame.columns:
        if token(c) in {"end date", "结束日期"}:
            if not (parse_dates(frame[c]).to_numpy() == data["date"].to_numpy()).all():
                raise ReportError("发现跨日期汇总行。请重新导出按日数据，不能拆分估算为日报。")
    numeric = [c for c in data if c not in ("date", "campaign", "ad_group", "targeting", "match_type", "search_term")]
    for c in numeric:
        try:
            data[c] = data[c].map(lambda v: number(v, scope.currency))
        except ReportError as exc:
            raise ReportError(f"{name} / {LABELS.get(c, c)}：{exc}") from exc
        if c not in ("sales", "spend", "ad_sales") and (data[c] % 1 != 0).any():
            raise ReportError(f"{LABELS[c]} 必须是整数。")
    for c in set(data) - set(numeric) - {"date"}:
        if data[c].isna().any() or data[c].astype(str).str.strip().eq("").any():
            raise ReportError(f"{name} 的 {LABELS[c]} 有空白。")
        data[c] = data[c].astype(str).str.strip()
    if kind == "ads" and (data["clicks"] > data["impressions"]).any():
        raise ReportError("点击量大于曝光量，请检查报表字段。")
    data["source"] = name
    data.attrs["mapping"] = json.dumps(mapping, ensure_ascii=False)
    return data


def combine(frames, kind):
    """Each later file replaces all rows of an overlapping date (one declared scope)."""
    if not frames:
        raise ReportError("请先导入文件。")
    result = None
    log = []
    keys = ["date"] if kind == "sales" else ["date", "campaign", "ad_group", "targeting", "match_type", "search_term"]
    optional = {"sessions", "page_views"}
    first_optional = optional & set(frames[0])
    for priority, original in enumerate(frames, 1):
        current = original.copy()
        if kind == "sales" and optional & set(current) != first_optional:
            raise ReportError("各文件的会话/浏览量字段不一致，请统一字段后再合并。")
        count = len(current)
        current = current.drop_duplicates()
        if current.duplicated(keys).any():
            raise ReportError(f"{current['source'].iloc[0]} 同一业务键有多行不同数值；请确认是否混入多个店铺或报表粒度。")
        replaced = 0
        if result is not None:
            overlap = result["date"].isin(current["date"])
            replaced = int(overlap.sum())
            result = result.loc[~overlap]
        result = current if result is None else pd.concat([result, current], ignore_index=True)
        log.append({"顺序": priority, "来源文件": current["source"].iloc[0], "原始行数": count,
                    "文件内完全重复行": count - len(current), "覆盖旧日期行数": replaced, "保留新行数": len(current),
                    "字段映射": original.attrs.get("mapping", ""), "SHA256": original.attrs.get("sha256", "")})
    return result.sort_values(keys).reset_index(drop=True), pd.DataFrame(log)


def divide(numerator, denominator):
    return numerator.div(denominator.where(denominator.ne(0)))


def sales_report(data):
    result = data.sort_values("date").copy()
    if "sessions" in result:
        result["unit_session_rate"] = divide(result["units"], result["sessions"])
    lookup = result.set_index("date")["sales"]
    for days, col in ((1, "sales_dod"), (7, "sales_wow")):
        previous = (result["date"] - pd.Timedelta(days=days)).map(lookup)
        result[col] = divide(result["sales"] - previous, previous)
    return result


def sales_brief(report, selected, scope):
    selected = pd.Timestamp(selected)
    found = report.loc[report["date"].eq(selected)]
    if found.empty:
        raise ReportError("所选日期没有数据。")
    row = found.iloc[0]
    def change(key):
        return "不可比（缺少对应日或分母为零）" if pd.isna(row[key]) else f"{row[key]:+.1%}"
    text = (f"【销售日报】{selected:%Y-%m-%d}\n店铺：{scope.store} | 站点：{scope.marketplace} | 币种：{scope.currency}\n"
            f"报表时区：{scope.timezone}\n订购商品销售额：{row['sales']:,.2f} {scope.currency}\n"
            f"订购件数：{row['units']:,.0f} | 订单项数：{row['order_items']:,.0f}\n"
            f"销售额较前一日：{change('sales_dod')}\n销售额较上周同日：{change('sales_wow')}\n")
    if "sessions" in row:
        ratio = "不可计算（会话数为零）" if pd.isna(row["unit_session_rate"]) else f"{row['unit_session_rate']:.2%}"
        text += f"会话数：{row['sessions']:,.0f} | 订购件数/会话数：{ratio}\n"
    return text + f"来源：{row['source']}\n说明：订购口径，非结算收入；订单项数非独立订单数。未推断变化原因。"


def ad_metrics(data):
    result = data.copy()
    for col, num, den in (("ctr", "clicks", "impressions"), ("cpc", "spend", "clicks"),
                          ("acos", "spend", "ad_sales"), ("roas", "ad_sales", "spend"),
                          ("ad_order_rate", "ad_orders", "clicks")):
        result[col] = divide(result[num], result[den])
    return result


def ads_report(data, scope, as_of, target_acos=0.3, min_clicks=20, min_spend=10.0):
    if not 0 < target_acos <= 10 or min_clicks < 1 or min_spend < 0:
        raise ReportError("请检查 ACOS 目标、最低点击量和花费门槛。")
    as_of = pd.Timestamp(as_of)
    if (data["date"] > as_of).any():
        raise ReportError("存在晚于分析截止日的数据，请调整截止日或输入范围。")
    detailed = ad_metrics(data)
    detailed["age"] = (as_of - detailed["date"]).dt.days
    detailed["mature"] = detailed["age"] > scope.window
    keys = ["campaign", "ad_group", "targeting", "match_type", "search_term"]
    sums = ["impressions", "clicks", "spend", "ad_sales", "ad_orders"]
    summary = ad_metrics(data.groupby(keys, as_index=False)[sums].sum())
    ready = detailed.loc[detailed["mature"]]
    candidates = ad_metrics(ready.groupby(keys, as_index=False)[sums].sum())
    candidates["status"] = "观察"
    candidates["reason"] = "未达到所设复核条件"
    candidates["action"] = "结合商品阶段继续观察"
    enough = (candidates["clicks"] >= min_clicks) & (candidates["spend"] >= min_spend)
    no_orders = enough & candidates["ad_orders"].eq(0)
    high = enough & candidates["ad_orders"].gt(0) & candidates["acos"].gt(target_acos)
    for mask, reason, action in (
        (no_orders, "完整等待样本达到门槛且归因订单为零", "人工核查搜索词相关性、页面与报价；由主管决定是否调整"),
        (high, "完整等待样本达到门槛且 ACOS 高于所设目标", "人工核查利润目标、相关性和近期变化后提交主管"),
    ):
        candidates.loc[mask, ["status", "reason", "action"]] = ["待复核", reason, action]
    candidates["review_note"] = ""
    candidates = candidates.sort_values(["status", "spend"], ascending=[True, False]).reset_index(drop=True)
    return detailed, summary, candidates


def display_table(frame):
    return frame.rename(columns=LABELS)


def excel_bytes(tables, metadata):
    """Create formula-free workbooks, including when uploaded text begins with '='."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    all_tables = {"范围与口径": pd.DataFrame(metadata, columns=["项目", "内容"]), **tables,
                  "使用说明": pd.DataFrame({"说明": NOTES})}
    rates = {"点击率", "ACOS", "归因订单数/点击量", "订购件数/会话数", "销售额较前一日", "销售额较上周同日"}
    for sheet_index, (name, frame) in enumerate(all_tables.items(), 1):
        sheet = workbook.create_sheet(name[:31])
        sheet.sheet_view.showGridLines = False
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.sheet_properties.tabColor = "168D9C"
        sheet.sheet_view.zoomScale = 90
        view = display_table(frame)
        sheet.append(list(view.columns))
        for row in view.itertuples(index=False, name=None):
            values = []
            for v in row:
                if pd.isna(v):
                    values.append(None)
                elif isinstance(v, pd.Timestamp):
                    values.append(v.to_pydatetime())
                elif hasattr(v, "item"):
                    values.append(v.item())
                else:
                    values.append(v)
            sheet.append(values)
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                elif isinstance(cell.value, (date, pd.Timestamp)):
                    cell.number_format = "yyyy-mm-dd"
                elif isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                    cell.number_format = "#,##0.00" if isinstance(cell.value, float) else "#,##0"
                cell.font = Font(name="Microsoft YaHei", size=10, color="234257")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="173C55")
            cell.font = Font(name="Microsoft YaHei", size=10, color="FFFFFF", bold=True)
        sheet.row_dimensions[1].height = 34
        for i in range(2, sheet.max_row + 1):
            sheet.row_dimensions[i].height = 28
        for i, header in enumerate(view.columns, 1):
            is_day = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(header)))
            width = 13 if is_day else 23
            if any(term in str(header) for term in ("说明", "原因", "备注", "方向", "依据", "内容", "字段映射")):
                width = 54
            if header in ("关键词", "客户搜索词"):
                width = 32
            sheet.column_dimensions[get_column_letter(i)].width = width
            if header in rates:
                for row in sheet.iter_rows(min_row=2, min_col=i, max_col=i):
                    row[0].number_format = "0.00%"
            if "改善名次" in str(header) and sheet.max_row > 1:
                cells = f"{get_column_letter(i)}2:{get_column_letter(i)}{sheet.max_row}"
                for operator, color, fill in (("greaterThan", "087F6D", "E1F4EF"), ("lessThan", "B74E48", "FCECE9")):
                    sheet.conditional_formatting.add(cells, CellIsRule(operator=operator, formula=["0"],
                        font=Font(color=color, bold=True), fill=PatternFill("solid", fgColor=fill)))
        sheet.freeze_panes = "A2"
        if "关键词" in view.columns and len(view.columns) > 3:
            sheet.freeze_panes = "D2"
        sheet.auto_filter.ref = sheet.dimensions
        if sheet.max_row > 1:
            table = Table(displayName=f"ReportTable{sheet_index}", ref=sheet.dimensions)
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            sheet.add_table(table)
        sheet.sheet_properties.outlinePr.summaryRight = False
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = "1:1"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
