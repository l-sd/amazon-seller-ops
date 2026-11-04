"""Update a supplied daily master workbook copy from explicit normalized exports."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from master_workbook import update_master  # noqa: E402
from operations import ReportError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="只更新运营总表副本的明确日期行，不覆盖原表或已有历史")
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    for kind in ("business", "ads", "pages", "ranks"):
        parser.add_argument(f"--{kind}", type=Path)
    args = parser.parse_args()
    audit = args.output.with_suffix(".audit.json")
    if audit.exists():
        parser.error("审计记录已存在，请使用新的输出文件名。")
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        inputs = {kind: getattr(args, kind) for kind in ("business", "ads", "pages", "ranks") if getattr(args, kind)}
        result = update_master(args.template, args.output, profile, args.date, inputs)
        with audit.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(json.dumps({"status": "ok", "output": str(args.output.resolve()), "row": result["row"],
                          "changed_cells": len(result["changes"]), "warnings": len(result["warnings"])}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, ReportError) as exc:
        parser.exit(2, f"未生成完整结果：{exc}\n")


if __name__ == "__main__":
    main()
