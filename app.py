"""Run with: streamlit run app.py --server.address 127.0.0.1"""

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from operations import (
    LABELS,
    NOTES,
    ReportError,
    Scope,
    ads_report,
    aliases,
    combine,
    display_table,
    excel_bytes,
    normalize,
    read_table,
    sales_brief,
    sales_report,
    suggest_mapping,
)
from rank_reports import HEADERS, consolidate, load_observations, rank_workbook

ROOT = Path(__file__).parent
st.set_page_config(page_title="亚马逊运营工作台", page_icon="📊", layout="wide")
st.markdown("""<style>
.stApp {background:#f6f8fb;} h1,h2,h3 {color:#173c55;}
[data-testid="stMetric"] {background:white;padding:18px;border:1px solid #e1e7ef;border-radius:12px;}
[data-testid="stSidebar"] {background:#edf2f7;}
</style>""", unsafe_allow_html=True)
st.title("亚马逊运营工作台")
st.caption("关键词追踪 · 销售日报 · SP 广告复盘 | 整理第三方导出，让每日变化清楚可见")

with st.sidebar:
    st.header("报表范围")
    mode = st.radio("数据来源", ["模拟数据体验", "导入自己的报表"])
    demo = mode == "模拟数据体验"
    store = st.text_input("店铺名称", "DEMO-STORE" if demo else "", disabled=demo)
    marketplace = st.selectbox("站点", ["US", "UK", "DE", "JP", "CA", "AU"])
    defaults = {"US": "USD", "UK": "GBP", "DE": "EUR", "JP": "JPY", "CA": "CAD", "AU": "AUD"}
    currency = st.text_input("币种", defaults[marketplace])
    timezone = st.text_input("报表时区（按导出设置填写）", "America/Los_Angeles" if marketplace == "US" else "")
    st.caption("每批仅处理同店铺、站点、币种和报表时区。系统不会自动判断无标识文件属于哪家店铺。")
    window = st.selectbox("SP 点击归因窗口（天）", [7, 14], disabled=demo)
    page = st.radio("工作模块", ["销售日报", "关键词日报", "广告报表复盘", "使用与口径"])

scope = Scope(store, marketplace, currency.strip().upper(), timezone, window)
RATE_CONFIG = {LABELS[k]: st.column_config.NumberColumn(format="percent") for k in
               ("ctr", "acos", "ad_order_rate", "unit_session_rate", "sales_dod", "sales_wow")}
if demo:
    st.warning("当前为模拟数据，不代表真实店铺经营或广告效果。切换到“导入自己的报表”可处理实际文件。")


def load_inputs(kind):
    if demo:
        names = ["sales_daily.csv"] if kind == "sales" else ["sp_search_terms_old.csv", "sp_search_terms_updated.csv"]
        inputs = [(n, (ROOT / "examples" / n).read_bytes()) for n in names]
    else:
        label = "按日期销售与流量报表" if kind == "sales" else "按日 SP 搜索词报表"
        files = st.file_uploader(f"上传{label}（可多选，单文件 ≤20 MB）", type=["csv", "tsv", "xlsx"],
                                 accept_multiple_files=True, key=f"upload_{kind}")
        if not files:
            st.info("请上传报表。也可以先用左侧模拟数据体验完整流程。")
            sample = "sales_daily.csv" if kind == "sales" else "sp_search_terms_updated.csv"
            st.download_button("下载模拟字段样例", (ROOT / "examples" / sample).read_bytes(), sample, "text/csv")
            return None
        if len({f.name for f in files}) != len(files):
            raise ReportError("文件名重复，请先在副本上使用不同文件名以便追溯。")
        inputs = [(f.name, f.getvalue()) for f in files]
        names = [n for n, _ in inputs]
        batch_key = hashlib.sha256("|".join(names).encode("utf-8")).hexdigest()[:12]
        order = st.multiselect("文件处理顺序：由旧到新，后一个覆盖重叠日期", names, default=names,
                               key=f"order_{kind}_{batch_key}")
        if set(order) != set(names):
            st.info("请选入全部文件，并按由旧到新的顺序排列。")
            return None
        inputs = [(n, dict(inputs)[n]) for n in order]
    st.caption("处理顺序：" + " → ".join(n for n, _ in inputs))
    st.caption("重叠日期以后一份文件的整日快照替换；请勿混入部分导出、不同广告类型或筛选范围的报表。")
    frames = []
    for i, (name, content) in enumerate(inputs):
        raw = read_table(name, content)
        guessed = suggest_mapping(raw.columns, kind, scope.window)
        mapping = {}
        with st.expander(f"字段映射与原始预览 · {name}", expanded=not demo and len(guessed) < len(aliases(kind, window))):
            st.dataframe(raw.head(5), hide_index=True)
            st.caption("日期按报表时区保留；斜杠日期按美式 MM/DD/YYYY 读取，其他地区请先用 YYYY-MM-DD。")
            if kind == "ads":
                st.caption(f"请选择 {window} 天的总归因销售额和订单数；通用 Sales / Orders 列须人工确认口径后映射。")
            for field in aliases(kind, window):
                options = ["（不提供）", *raw.columns]
                default = guessed.get(field, "（不提供）")
                selected = st.selectbox(LABELS[field], options, index=options.index(default),
                                        key=f"map_{kind}_{i}_{name}_{field}_{window}")
                if selected != "（不提供）":
                    mapping[field] = selected
        normalized = normalize(raw, kind, mapping, scope, name)
        normalized.attrs["sha256"] = hashlib.sha256(content).hexdigest()
        frames.append(normalized)
    return combine(frames, kind)


def metadata(kind):
    return [("模块", kind), ("店铺", scope.store), ("站点", scope.marketplace), ("币种", scope.currency),
            ("报表时区", scope.timezone), ("数据来源", "模拟数据" if demo else "用户导入，范围由用户确认"),
            ("生成日期", date.today().isoformat()), ("覆盖规则", "按界面顺序，后文件替换整个重叠日期")]


try:
    if page == "使用与口径":
        st.subheader("使用前核对")
        st.markdown("1. 从对应后台导出按日数据。\n2. 填写报表范围，上传文件并检查映射。\n"
                    "3. 确认文件由旧到新、每份都包含对应日期的完整范围。\n4. 下载 Excel，人工复核并记录动作。")
        for note in NOTES:
            st.markdown(f"- {note}")
        st.info("文件由本机程序处理，不接入店铺、不调用 AI 服务。不要将真实报表或导出结果上传到公开 GitHub。")
        st.markdown("[查看项目说明与支持范围](https://sellercentral.amazon.com/help/hub/reference/external/202142060)")
    elif page == "关键词日报":
        st.subheader("关键词排名日报")
        st.write("网站负责查询排名；这里整理返回的表格，保留历史并计算同口径的每日变化。")
        if demo:
            files = [("keyword_ranks.csv", (ROOT / "examples/keyword_ranks.csv").read_bytes())]
        else:
            uploads = st.file_uploader("上传标准化排名表与上一版历史（可多选）", type=["csv", "tsv", "xlsx"],
                                       accept_multiple_files=True, key="rank_upload")
            files = [(f.name, f.getvalue()) for f in uploads]
            st.caption("首次导入实际网站的表格，请让 Skill 核对列名、采集时间和状态码并标准化。不会猜测缺失的采集范围。")
            st.download_button("下载排名字段模板", (ROOT / ".agents/skills/amazon-seller-ops/assets/keyword-ranks.csv").read_bytes(),
                               "keyword-ranks-template.csv", "text/csv")
        if files:
            rows = []
            for name, content in files:
                batch, _ = load_observations(Path(name), "synthetic" if demo else "user-provided", {}, content)
                rows.extend(batch)
            history, daily = consolidate(rows)
            asin = st.selectbox("查看 ASIN", sorted(daily["asin"].unique()))
            kind = st.radio("排名口径", ["自然排名", "SP 广告排名"], horizontal=True)
            selected_kind = "organic" if kind == "自然排名" else "sponsored_sp"
            view = daily.loc[daily["asin"].eq(asin) & daily["rank_type"].eq(selected_kind)]
            contexts = ["provider", "marketplace", "rank_definition", "device", "delivery_region", "sampling_rule", "timezone"]
            choices = view[contexts].drop_duplicates().to_dict(orient="records")
            if len(choices) > 1:
                selected_scope = st.selectbox("选择同一监控范围", range(len(choices)),
                    format_func=lambda i: " / ".join(str(v) for v in choices[i].values()))
                for key, value in choices[selected_scope].items():
                    view = view.loc[view[key].eq(value)]
            if view.empty:
                st.info("当前 ASIN 没有此排名类型，请切换口径。")
                st.stop()
            latest = view.loc[view["date"].eq(view["date"].max())]
            a, b, c, d = st.columns(4)
            a.metric("监控词数", len(latest))
            b.metric("较前日改善", int(latest["change_1d"].gt(0).sum()))
            c.metric("较前日下降", int(latest["change_1d"].lt(0).sum()))
            d.metric("非数值状态", int(latest["status"].ne("found").sum()))
            st.caption(f"最新实际采集日期：{view['date'].max()}。改善名次为旧排名减新排名；非数值状态不填 0。")
            display = latest[["keyword", "rank", "change_1d", "change_7d", "status", "comparison_note"]].rename(columns=HEADERS)
            st.dataframe(display, hide_index=True, use_container_width=True)
            chart = view.pivot(index="date", columns="keyword", values="rank")
            st.line_chart(chart)
            st.caption("排名数值越小越靠前。换工具、设备、配送地区或排名定义时，不应拼接为同一趋势。")
            st.download_button("下载关键词日报 Excel", rank_workbook(history, daily, "synthetic" if demo else "user-provided"),
                               "keyword_ranks.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("保存历史供下次更新", history.to_csv(index=False).encode("utf-8-sig"), "rank_history.csv", "text/csv")
        else:
            st.info("上传第三方工具导出的标准化排名表后生成结果；也可以切换模拟数据体验。")
    elif page == "销售日报":
        st.subheader("销售日报")
        st.write("按店铺日期整理订购表现，自动比较前一日和上周同日，生成可复制的日报。")
        loaded = load_inputs("sales")
        if loaded is not None:
            data, log = loaded
            report = sales_report(data)
            selected = st.selectbox("日报日期", report["date"].dt.date.tolist(), index=len(report) - 1)
            row = report.loc[report["date"].eq(pd.Timestamp(selected))].iloc[0]
            a, b, c = st.columns(3)
            a.metric(f"订购商品销售额 · {scope.currency}", f"{row['sales']:,.2f}")
            b.metric("订购件数", f"{row['units']:,.0f}")
            c.metric("订单项数（非独立订单数）", f"{row['order_items']:,.0f}")
            st.line_chart(report.set_index("date")[["sales"]].rename(columns=LABELS))
            brief = sales_brief(report, selected, scope)
            st.text_area("日报文案（可复制）", brief, height=245)
            st.dataframe(display_table(report), hide_index=True, column_config=RATE_CONFIG)
            st.subheader("导入与校验记录")
            st.dataframe(log, hide_index=True)
            st.caption(f"有效日期 {len(report)} 天；销售额回算 {report['sales'].sum():,.2f} {scope.currency}。"
                       "缺失日期不填零；当日未结束或导出未完整时请谨慎解读。")
            tables = {"销售日报": report, "导入记录": log, "日报文案": pd.DataFrame({"内容": brief.splitlines()})}
            book = excel_bytes(tables, metadata("销售日报"))
            st.download_button("下载销售日报 Excel", book, "sales_daily_report.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("下载日报文案", brief.encode("utf-8-sig"), "sales_daily_brief.txt", "text/plain")
    else:
        st.subheader("SP 搜索词报表复盘")
        st.write("自动汇总并生成待复核清单，保留原始依据和人工处理备注。")
        loaded = load_inputs("ads")
        if loaded is not None:
            data, log = loaded
            a, b, c, d = st.columns(4)
            as_of = a.date_input("分析截止日（含当天）", date(2026, 11, 3) if demo else date.today())
            target = b.number_input("ACOS 目标（%）", min_value=1.0, max_value=1000.0, value=30.0, step=1.0) / 100
            clicks = c.number_input("复核最低点击量", min_value=1, value=20)
            spend = d.number_input(f"复核最低花费 · {scope.currency}", min_value=0.0, value=10.0)
            detail, summary, candidates = ads_report(data, scope, as_of, target, clicks, spend)
            first = ["status", "search_term", "spend", "ad_orders", "ad_sales", "acos", "reason", "action", "review_note"]
            candidates = candidates[first + [col for col in candidates if col not in first]]
            a, b, c = st.columns(3)
            a.metric(f"所导入搜索词花费 · {scope.currency}", f"{data['spend'].sum():,.2f}")
            b.metric("待复核目标数", int(candidates["status"].eq("待复核").sum()))
            c.metric("归因仍需等待的行数", int((~detail["mature"]).sum()))
            st.info("下方复核清单仅使用日期距截止日大于归因窗口的数据；阈值是你的筛选条件。"
                    "近期数据在完整汇总和明细中保留。搜索词报表不代表全部广告曝光。")
            tab1, tab2, tab3 = st.tabs(["待复核与行动记录", "全部日期汇总", "明细与导入记录"])
            with tab1:
                st.caption("可直接填写人工备注，修改后会进入本次 Excel。刷新页面或换文件后请重新核对。")
                edited = st.data_editor(display_table(candidates), hide_index=True, use_container_width=True,
                                        column_config=RATE_CONFIG,
                                        disabled=[LABELS.get(col, col) for col in candidates if col != "review_note"],
                                        key="review_editor")
                if candidates.empty:
                    st.warning("当前没有完整等待归因的日期，暂不生成动作候选。")
            with tab2:
                st.dataframe(display_table(summary), hide_index=True, column_config=RATE_CONFIG)
            with tab3:
                st.dataframe(display_table(detail), hide_index=True, column_config=RATE_CONFIG)
                st.dataframe(log, hide_index=True)
            meta = metadata("SP 搜索词复盘") + [("点击归因窗口（天）", str(window)), ("分析截止日", str(as_of)),
                    ("ACOS 目标", f"{target:.2%}"), ("最低点击量", str(clicks)), ("最低花费", str(spend)),
                    ("复核样本", "距截止日天数大于归因窗口；不证明平台最终结算"),
                    ("金额回算", f"导入花费={data['spend'].sum():.2f}；汇总花费={summary['spend'].sum():.2f}")]
            book = excel_bytes({"复核与行动记录": edited, "全部日期汇总": summary, "广告明细": detail, "导入记录": log}, meta)
            st.download_button("下载广告复盘 Excel", book, "sp_search_term_review.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
except ReportError as exc:
    st.error(str(exc))
    st.caption("本次未生成结果。请核对原始文件及字段映射；系统不会静默丢弃异常行。")
