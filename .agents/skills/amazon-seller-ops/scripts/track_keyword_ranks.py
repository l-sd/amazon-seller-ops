"""Consolidate exported rank observations, preserving collection times and scope."""

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from operations import ReportError, excel_bytes, read_table  # noqa: E402

GROUP = ["provider", "marketplace", "asin", "keyword", "rank_type", "rank_definition", "device",
         "delivery_region", "sampling_rule", "timezone", "data_kind"]
FIELDS = GROUP[:-1] + ["observed_at", "rank", "status", "search_limit", "source_reference"]
STATUS = {"found": "找到排名", "out_of_range": "超出采集范围", "not_collected": "未采集", "unavailable": "采集失败/不可访问"}
HEADERS = {"provider": "数据工具", "marketplace": "站点", "asin": "ASIN", "keyword": "关键词",
           "rank_type": "排名类型", "rank_definition": "排名定义", "device": "设备", "delivery_region": "配送地区",
           "sampling_rule": "采样规则", "timezone": "数据时区", "data_kind": "数据性质", "observed_at": "实际采集时间",
           "rank": "排名", "status": "采集状态", "search_limit": "采集范围上限", "source_reference": "来源依据",
           "source_file": "来源文件", "date": "采集日期", "change_1d": "较前日改善名次", "change_7d": "较上周同日改善名次",
           "comparison_note": "比较说明"}


def positive_int(value, field):
    if not value:
        return None
    try:
        number = Decimal(value)
        if not number.is_finite() or number <= 0 or number != number.to_integral_value():
            raise InvalidOperation
        return int(number)
    except InvalidOperation as exc:
        raise ReportError(f"{field} 只能是正整数或空白，不能把 0、横线或 >N 自动当排名。") from exc


def load_observations(path, data_kind, config, content=None):
    content = path.read_bytes() if content is None else content
    raw = read_table(path.name, content).fillna("")
    mapping = config.get(path.name)
    if mapping is not None:
        if not isinstance(mapping, dict) or len(set(mapping.values())) != len(mapping):
            raise ReportError("字段映射须为目标字段到原表列名的一对一 JSON 对象。")
        if any(name not in raw for name in mapping.values()):
            raise ReportError("映射包含不存在的来源列。")
        raw = raw[list(mapping.values())].rename(columns={v: k for k, v in mapping.items()})
    required = set(FIELDS) - {"rank", "search_limit"}
    if required - set(raw):
        raise ReportError(f"{path.name} 缺少字段：{', '.join(sorted(required - set(raw)))}。请检查模板和映射。")
    rows = []
    for item in raw.to_dict(orient="records"):
        row = {k: str(item.get(k, "")).strip() for k in FIELDS}
        if any(not row[k] for k in required):
            raise ReportError("关键词、具体 ASIN、采集时间或比较范围等必填信息缺失；不能用导出时间猜测采集时间。")
        if item.get("data_kind") and item["data_kind"] != data_kind:
            raise ReportError("历史与新数据的数据性质不同，模拟数据不能混入真实记录。")
        row["data_kind"] = data_kind
        row["keyword"] = re.sub(r"\s+", " ", row["keyword"]).casefold()
        if not re.fullmatch(r"[A-Z0-9]{10}", row["asin"]):
            raise ReportError("ASIN 须为 10 位大写字母或数字。")
        if row["rank_type"] not in {"organic", "sponsored_sp", "sponsored_sb"}:
            raise ReportError("请区分 organic、sponsored_sp 或 sponsored_sb；不能把 ABA 排名混入。")
        if row["rank_definition"] not in {"absolute", "slot"} or (row["rank_type"] == "organic" and row["rank_definition"] != "absolute"):
            raise ReportError("仅支持明确的绝对排名或广告位 slot；不自动折算页码/页内位置。")
        if row["sampling_rule"] != "daily_latest":
            raise ReportError("当前脚本仅支持 daily_latest（每日最后一次采集），其他统计口径需另行处理。")
        if row["status"] not in STATUS:
            raise ReportError("未知状态码；先核对供应商对缺失/超范围/失败的定义，再映射。")
        row["rank"] = positive_int(row["rank"], "排名")
        row["search_limit"] = positive_int(row["search_limit"], "采集上限")
        if (row["status"] == "found") != (row["rank"] is not None):
            raise ReportError("只有 found 能填写排名，且必须有正整数排名；其余状态排名留空。")
        if row["status"] == "out_of_range" and row["search_limit"] is None:
            raise ReportError("超范围记录必须提供实际采集上限。")
        if row["rank"] and row["search_limit"] and row["rank"] > row["search_limit"]:
            raise ReportError("找到的排名超过声明的采集上限。")
        try:
            moment = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
            if moment.utcoffset() is None:
                raise ValueError("timezone missing")
            moment = moment.astimezone(ZoneInfo(row["timezone"]))
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ReportError("采集时间须带时区；timezone 须为有效 IANA 时区，例如 America/Los_Angeles。") from exc
        row["observed_at"] = moment.isoformat()
        row["date"] = moment.date().isoformat()
        row["_utc"] = moment.astimezone(UTC)
        row["source_file"] = str(item.get("source_file") or path.name)
        rows.append(row)
    return rows, {"file": path.name, "sha256": hashlib.sha256(content).hexdigest(), "rows": len(rows)}


def consolidate(rows):
    unique = {}
    for row in rows:
        key = tuple(row[k] for k in GROUP) + (row["_utc"],)
        if key in unique and any(unique[key][c] != row[c] for c in ("rank", "status", "search_limit")):
            raise ReportError("同范围、同一采集时间出现冲突排名，请核对来源，不静默覆盖。")
        unique.setdefault(key, row)
    history = sorted(unique.values(), key=lambda r: (tuple(r[k] for k in GROUP), r["_utc"]))
    daily = {}
    for row in history:
        daily[tuple(row[k] for k in GROUP) + (row["date"],)] = row
    results = []
    for key, row in sorted(daily.items()):
        current = {k: v for k, v in row.items() if k != "_utc"}
        notes = []
        for days, field in ((1, "change_1d"), (7, "change_7d")):
            previous_date = (datetime.fromisoformat(row["date"]).date() - timedelta(days=days)).isoformat()
            previous = daily.get(key[:-1] + (previous_date,))
            current[field] = None
            if previous is None:
                notes.append(f"{days}天前无同口径记录")
            elif row["status"] == previous["status"] == "found":
                current[field] = previous["rank"] - row["rank"]
            else:
                notes.append(f"{days}天比较不可计算：当前{STATUS[row['status']]}，此前{STATUS[previous['status']]}")
        current["comparison_note"] = "；".join(notes) or "正值改善、负值下降；不证明变化原因"
        results.append(current)
    clean_history = [{k: v for k, v in row.items() if k != "_utc"} for row in history]
    return pd.DataFrame(clean_history), pd.DataFrame(results)


def rank_workbook(history, daily, data_kind):
    value = daily.copy()
    value["cell"] = value.apply(lambda r: int(r["rank"]) if r["status"] == "found" else STATUS[r["status"]], axis=1)
    pivot = value.pivot(index=GROUP, columns="date", values="cell").reset_index()
    context = [col for col in GROUP if col not in ("asin", "keyword", "rank_type")]
    fixed = [col for col in context if daily.groupby(["asin", "keyword", "rank_type"])[col].nunique().max() == 1]
    matrix = pivot.drop(columns=fixed)
    today = daily.loc[daily["date"].eq(daily["date"].max())].copy()
    today_cols = ["asin", "keyword", "rank_type", "rank", "change_1d", "change_7d", "status", "comparison_note"]
    today = today[today_cols]
    today["status"] = today["status"].map(STATUS)
    metadata = [("任务", "第三方排名表整理"), ("数据性质", data_kind), ("日取样", "daily_latest，每日最后一次实际采集"),
                ("比较", "仅比较前一自然日/上周同日；正值是改善名次"), ("范围", "工具/站点/ASIN/词/类型/定义/设备/地区/时区隔离"),
                ("缺失", "未采集、超范围和失败分开；不填零、不编造历史"), ("运行方式", "按需处理文件，未连接供应商或设置定时任务")]
    return excel_bytes({"今日关注": today.rename(columns=HEADERS), "每日排名": matrix.rename(columns=HEADERS),
                        "逐日变化": daily.rename(columns=HEADERS), "采集历史": history.rename(columns=HEADERS),
                        "监控范围": daily[context].drop_duplicates().rename(columns=HEADERS)}, metadata)


def main(argv=None):
    parser = argparse.ArgumentParser(description="整理第三方工具返回的关键词排名表，不查询或抓取排名")
    parser.add_argument("--input", nargs="+", type=Path, required=True)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--data-kind", choices=["synthetic", "user-provided"], required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("输出目录已存在，请换新目录保护历史文件。")
    try:
        config = json.loads(args.mapping.read_text(encoding="utf-8-sig")) if args.mapping else {}
        if not isinstance(config, dict):
            raise ReportError("映射须为按文件名分组的 JSON 对象。")
        rows, sources = [], []
        paths = ([args.history] if args.history else []) + args.input
        for path in paths:
            batch, source = load_observations(path, args.data_kind, config)
            rows.extend(batch)
            sources.append(source)
        history, daily = consolidate(rows)
        excel = rank_workbook(history, daily, args.data_kind)
        manifest = {"sources": sources, "data_kind": args.data_kind, "input_rows": len(rows),
                    "history_rows": len(history), "daily_rows": len(daily), "deduplicated_rows": len(rows) - len(history)}
        args.output_dir.mkdir(parents=True, exist_ok=False)
        history.to_csv(args.output_dir / "rank_history.csv", index=False, encoding="utf-8-sig")
        (args.output_dir / "keyword_ranks.xlsx").write_bytes(excel)
        (args.output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "output": str(args.output_dir.resolve()), **manifest}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"未生成完整结果：{exc}\n")


if __name__ == "__main__":
    main()
