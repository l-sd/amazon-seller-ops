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
    # Keyword ideas are based on a public Amazon US listing for a RUGSREAL
    # 5 x 7 grey washable rug. Only the product wording is real; all ranks below
    # are generated practice data.
    keywords = [
        ("area rug", 48, 0.1),
        ("area rugs", 72, 0.2),
        ("living room rug", 38, -0.3),
        ("area rugs for living room", 34, -0.4),
        ("5x7 area rug", 18, -0.2),
        ("5x7 rug for living room", 46, 0.1),
        ("machine washable rug", 32, -0.5),
        ("washable area rug", 24, -0.4),
        ("machine washable area rug", 39, -0.3),
        ("boho area rug", 63, 0.2),
        ("geometric area rug", 42, -0.2),
        ("farmhouse rug", 76, 0.3),
        ("farmhouse area rug", 68, 0.2),
        ("modern area rug", 57, -0.1),
        ("non slip area rug", 28, -0.5),
        ("non slip washable rug", 44, -0.3),
        ("stain resistant rug", 51, 0.1),
        ("low pile area rug", 37, -0.2),
        ("grey area rug", 55, 0.2),
        ("grey area rug 5x7", 29, -0.4),
        ("pet friendly area rug", 61, -0.3),
        ("living room area rug 5x7", 33, -0.4),
        ("dining room rug", 81, 0.2),
        ("bedroom area rug", 70, 0.1),
        ("home office rug", 90, -0.2),
        ("entryway rug", 95, 0.2),
        ("chenille area rug", 48, 0.1),
        ("rubber backing rug", 87, -0.1),
        ("5x7 washable rug", 27, -0.5),
        ("machine washable rug for living room", 59, -0.4),
        ("geometric washable rug", 35, -0.4),
        ("modern geometric area rug", 53, -0.2),
        ("washable rug for home office", 74, -0.2),
        ("boho geometric rug", 47, 0.1),
        ("non slip rug for bedroom", 64, -0.3),
        ("stain resistant living room rug", 69, -0.2),
    ]
    for i, day in enumerate(pd.date_range("2026-10-21", periods=14)):
        for product in ("B0DEMO0001", "B0DEMO0002"):
            for j, (word, base, trend) in enumerate(keywords):
                for kind in ("organic", "sponsored_sp"):
                    if kind == "sponsored_sp":
                        value = 1 + (i * 2 + j) % 11 + (2 if product.endswith("2") else 0)
                    else:
                        fluctuation = ((i + j * 2) % 5 - 2) * 2
                        value = max(1, round(base + i * trend + fluctuation + (9 if product.endswith("2") else 0)))
                    status = "found"
                    if i == 12 and j == 17 and kind == "organic":
                        status, value = "not_collected", ""
                    if i == 13 and j == 27 and product.endswith("1") and kind == "organic":
                        status, value = "out_of_range", ""
                    ranks.append({"provider": "DEMO-EXPORT", "marketplace": "US", "asin": product, "keyword": word,
                                  "rank_type": kind, "rank_definition": "absolute" if kind == "organic" else "slot",
                                  "device": "desktop", "delivery_region": "US-10001", "sampling_rule": "daily_latest",
                                  "timezone": "America/Los_Angeles", "observed_at": f"{day:%Y-%m-%d}T10:00:00-07:00",
                                  "rank": value, "status": status, "search_limit": 306,
                                  "source_reference": "synthetic://rugsreal-keyword-showcase", "data_kind": "synthetic"})
    pd.DataFrame(ranks).to_csv(target / "keyword_ranks.csv", index=False, encoding="utf-8-sig")
    print("Generated 4 synthetic CSV files; no real store data.")


if __name__ == "__main__":
    main()
