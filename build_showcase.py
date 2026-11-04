"""Build public, synthetic-only showcase data from the same rank engine as the Skill."""

import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from rank_reports import consolidate, load_observations, rank_workbook
from simulate_master import run_simulation

ROOT = Path(__file__).parent
PRODUCT_PAGE = (
    "https://www.shopabunda.com/products/"
    "rugsreal-5-x-7-machine-washable-area-rug-boho-geometric-area-rug-"
    "farmhouse-non-slip-stain-resistant-modern-rug-for-living-room-home-office-5-x-7"
)
AMAZON_SEARCH = "https://www.amazon.com/s?k=RUGSREAL+5+x+7+machine+washable+area+rug"


def main():
    rows, source = load_observations(ROOT / "examples/keyword_ranks.csv", "synthetic", {})
    history, daily = consolidate(rows)
    records = daily.astype(object).where(pd.notna(daily), None).to_dict(orient="records")
    payload = {
        "data_kind": "synthetic",
        "updated": str(daily["date"].max()),
        "records": records,
        "source": source,
        "products": [
            {"asin": "B0DEMO0001", "name": "RUGSREAL · 5×7 灰色可洗地毯"},
            {"asin": "B0DEMO0002", "name": "同类商品对照（模拟）"},
        ],
        "product_reference": {
            "brand": "RUGSREAL",
            "title": "5 x 7 Machine Washable Area Rug Boho Geometric Area Rug",
            "details": "Grey · Chenille · Low pile · Machine wash · Non-slip · Stain resistant",
            "source_url": PRODUCT_PAGE,
            "amazon_search_url": AMAZON_SEARCH,
            "checked_on": "2026-11-04",
        },
        "note": "关键词根据公开商品标题和卖点整理；所有排名与走势均为程序生成的模拟数据。",
    }
    (ROOT / "docs/demo-data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs/keyword-ranks-demo.xlsx").write_bytes(rank_workbook(history, daily, "synthetic"))
    # Always generate a clean template, never use a supplied workbook for public assets.
    destination = ROOT / "outputs" / f"showcase-master-{uuid4().hex[:10]}"
    summary = run_simulation(destination)
    (ROOT / "docs/master-demo.xlsx").write_bytes((destination / summary["final_workbook"]).read_bytes())
    print(f"Built synthetic showcase: {len(history)} observations / {len(daily)} daily samples")


if __name__ == "__main__":
    main()
