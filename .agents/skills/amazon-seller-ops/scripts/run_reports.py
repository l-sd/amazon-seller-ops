"""Command-line access to the repository's validated report engine."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if not (ROOT / "operations.py").is_file():
    raise SystemExit("缺少仓库根目录 operations.py；请在完整项目中使用报表工具。研究流程仍可单独使用。")
sys.path.insert(0, str(ROOT))

from operations import (  # noqa: E402
    ReportError,
    Scope,
    ads_report,
    combine,
    excel_bytes,
    normalize,
    read_table,
    sales_brief,
    sales_report,
    suggest_mapping,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="销售日报或 SP 搜索词复盘，只读输入并创建新输出目录")
    parser.add_argument("mode", choices=["sales", "ads"])
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    for name in ("store", "marketplace", "currency", "timezone"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--data-kind", choices=["synthetic", "user-provided"], required=True)
    parser.add_argument("--window", choices=[7, 14], type=int, default=7)
    parser.add_argument("--as-of", help="广告必填，实际导出观察截止日 YYYY-MM-DD")
    parser.add_argument("--report-date", help="日报日期 YYYY-MM-DD，省略时使用输入最后一日")
    parser.add_argument("--target-acos", type=float, default=0.30)
    parser.add_argument("--min-clicks", type=int, default=20)
    parser.add_argument("--min-spend", type=float, default=10)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("输出目录已存在；请换新目录以保护已有产物。")
    if args.mode == "ads" and not args.as_of:
        parser.error("广告复盘必须填写 --as-of，不猜测导出时间。")
    if not all(math.isfinite(x) for x in (args.target_acos, args.min_spend)):
        parser.error("筛选条件必须是有限数。")
    if len({p.name for p in args.input}) != len(args.input):
        parser.error("输入文件名重复，请在副本上使用不同文件名便于追溯。")
    try:
        scope = Scope(args.store, args.marketplace, args.currency.upper(), args.timezone, args.window)
        scope.validate()
        config = json.loads(args.mapping.read_text(encoding="utf-8-sig")) if args.mapping else {}
        if not isinstance(config, dict):
            raise ReportError("映射文件应是按文件名分组的 JSON 对象。")
        frames, sources = [], []
        for path in args.input:
            content = path.read_bytes()
            raw = read_table(path.name, content)
            mapping = config.get(path.name, suggest_mapping(raw.columns, args.mode, args.window))
            if not isinstance(mapping, dict):
                raise ReportError(f"{path.name} 的映射必须是 JSON 对象。")
            frame = normalize(raw, args.mode, mapping, scope, path.name)
            digest = hashlib.sha256(content).hexdigest()
            frame.attrs["sha256"] = digest
            frames.append(frame)
            sources.append({"file": path.name, "sha256": digest, "mapping": mapping})
        data, log = combine(frames, args.mode)
        meta = [("任务", args.mode), ("店铺", scope.store), ("站点", scope.marketplace), ("币种", scope.currency),
                ("报表时区", scope.timezone), ("数据性质", args.data_kind),
                ("覆盖规则", "输入由旧到新，整个重叠日期替换"), ("输入真实性", "调用方提供；脚本不认证来源")]
        manifest = {"mode": args.mode, "data_kind": args.data_kind, "scope": vars(scope), "sources": sources,
                    "import_log": log.to_dict(orient="records"), "rows_after_merge": len(data)}
        files = {}
        if args.mode == "sales":
            report = sales_report(data)
            selected = args.report_date or data["date"].max().date().isoformat()
            brief = sales_brief(report, selected, scope)
            manifest.update(report_date=selected, sales_total=float(report["sales"].sum()))
            files["sales_daily.xlsx"] = excel_bytes({"销售日报": report, "导入记录": log}, meta)
            files["sales_brief.txt"] = (f"数据性质：{args.data_kind}\n" + brief).encode("utf-8-sig")
        else:
            detail, summary, review = ads_report(data, scope, args.as_of, args.target_acos,
                                                args.min_clicks, args.min_spend)
            spent = float(data["spend"].sum())
            summed = float(summary["spend"].sum())
            if abs(spent - summed) > 0.000001:
                raise ReportError("花费汇总校验失败，未导出。")
            meta += [("观察截止日", args.as_of), ("归因窗口", str(args.window)),
                     ("复核条件", f"ACOS={args.target_acos};点击>={args.min_clicks};花费>={args.min_spend}"),
                     ("花费回算", f"输入 {spent:.2f}；汇总 {summed:.2f}")]
            manifest.update(as_of=args.as_of, target_acos=args.target_acos, min_clicks=args.min_clicks,
                            min_spend=args.min_spend, spend_total=spent,
                            pending_rows=int((~detail["mature"]).sum()),
                            review_candidates=int(review["status"].eq("待复核").sum()))
            files["sp_review.xlsx"] = excel_bytes({"广告明细": detail, "全部日期汇总": summary,
                                                  "复核与行动记录": review, "导入记录": log}, meta)
        files["run_manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            with (args.output_dir / name).open("xb") as handle:
                handle.write(content)
        print(json.dumps({"status": "ok", "mode": args.mode, "output": str(args.output_dir.resolve()),
                          "files": list(files)}, ensure_ascii=False))
    except (ReportError, OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"未生成完整结果：{exc}\n")


if __name__ == "__main__":
    main()
