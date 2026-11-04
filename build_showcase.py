"""Build public, synthetic-only showcase data from the same rank engine as the Skill."""

import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from rank_reports import consolidate, load_observations, rank_workbook
from simulate_master import run_simulation

ROOT = Path(__file__).parent


def main():
    rows, source = load_observations(ROOT / "examples/keyword_ranks.csv", "synthetic", {})
    history, daily = consolidate(rows)
    records = daily.astype(object).where(pd.notna(daily), None).to_dict(orient="records")
    payload = {"data_kind": "synthetic", "updated": str(daily["date"].max()), "records": records,
               "source": source, "note": "所有商品、ASIN 和排名都是模拟案例，不是西柚导出或真实经营数据"}
    (ROOT / "docs/demo-data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs/keyword-ranks-demo.xlsx").write_bytes(rank_workbook(history, daily, "synthetic"))
    # Always generate a clean template, never use a supplied workbook for public assets.
    destination = ROOT / "outputs" / f"showcase-master-{uuid4().hex[:10]}"
    summary = run_simulation(destination)
    (ROOT / "docs/master-demo.xlsx").write_bytes((destination / summary["final_workbook"]).read_bytes())
    print(f"Built synthetic showcase: {len(history)} observations / {len(daily)} daily samples")


if __name__ == "__main__":
    main()
