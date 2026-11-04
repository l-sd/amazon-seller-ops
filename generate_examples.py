"""Generate deterministic, fictitious, schema-oriented practice files."""

from pathlib import Path

import pandas as pd


def main():
    target = Path(__file__).parent / "examples"
    target.mkdir(exist_ok=True)
    dates = pd.date_range("2026-10-12", periods=21)
    sales = []
    ads = []
    terms = [("desk organizer", 45, 3, 60), ("free organizer", 30, 0, 0), ("small desk tray", 24, 1, 20),
             ("B0DEMO0001", 12, 1, 30)]
    for i, day in enumerate(dates):
        units = 20 + (i * 7) % 21
        sales.append({"Date": day.strftime("%m/%d/%Y"), "Ordered Product Sales": f"${units * 19.9:,.2f}",
                      "Units Ordered": units, "Total Order Items": units - 3, "Sessions - Total": 180 + i * 8,
                      "Page Views - Total": 260 + i * 10, "Store": "DEMO-STORE", "Marketplace": "US", "Currency": "USD"})
        for term, clicks, orders, revenue in terms:
            ads.append({"Date": day.strftime("%Y-%m-%d"), "Campaign Name": "DEMO-SP-Desk", "Ad Group Name": "DEMO-Group",
                        "Targeting": "close-match", "Match Type": "-", "Customer Search Term": term,
                        "Impressions": clicks * 30, "Clicks": clicks, "Spend": round(clicks * 0.65, 2),
                        "7 Day Total Orders (#)": orders, "7 Day Total Sales": revenue,
                        "Store": "DEMO-STORE", "Marketplace": "US", "Currency": "USD", "Ad Product": "SPONSORED_PRODUCTS"})
    pd.DataFrame(sales).to_csv(target / "sales_daily.csv", index=False, encoding="utf-8-sig")
    old = pd.DataFrame(ads[:15 * 4])
    old.to_csv(target / "sp_search_terms_old.csv", index=False, encoding="utf-8-sig")
    updated = pd.DataFrame(ads[10 * 4:])
    updated.loc[updated["Customer Search Term"].eq("desk organizer"), "7 Day Total Orders (#)"] = 4
    updated.loc[updated["Customer Search Term"].eq("desk organizer"), "7 Day Total Sales"] = 80
    updated.to_csv(target / "sp_search_terms_updated.csv", index=False, encoding="utf-8-sig")
    ranks = []
    keywords = ["desk organizer", "office desk tray", "small desk organizer", "desktop storage"]
    for i, day in enumerate(pd.date_range("2026-10-21", periods=14)):
        for product in ("B0DEMO0001", "B0DEMO0002"):
            for j, word in enumerate(keywords):
                for kind in ("organic", "sponsored_sp"):
                    value = [72 - i * 3, 18 + i * 2, 90 - i * 2, 15 + i % 4][j]
                    if product.endswith("2"):
                        value += 5
                    if kind == "sponsored_sp":
                        value = 2 + (i + j) % 5
                    status = "found"
                    if i == 12 and j == 2 and kind == "organic":
                        status, value = "not_collected", ""
                    if i == 13 and j == 3 and product.endswith("1") and kind == "organic":
                        status, value = "out_of_range", ""
                    ranks.append({"provider": "DEMO-EXPORT", "marketplace": "US", "asin": product, "keyword": word,
                                  "rank_type": kind, "rank_definition": "absolute" if kind == "organic" else "slot",
                                  "device": "desktop", "delivery_region": "US-10001", "sampling_rule": "daily_latest",
                                  "timezone": "America/Los_Angeles", "observed_at": f"{day:%Y-%m-%d}T10:00:00-07:00",
                                  "rank": value, "status": status, "search_limit": 306,
                                  "source_reference": "synthetic://rank-export-example", "data_kind": "synthetic"})
    pd.DataFrame(ranks).to_csv(target / "keyword_ranks.csv", index=False, encoding="utf-8-sig")
    print("Generated 4 synthetic CSV files; no real store data.")


if __name__ == "__main__":
    main()
