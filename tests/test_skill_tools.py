import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents" / "skills" / "amazon-seller-ops" / "scripts"
spec = importlib.util.spec_from_file_location("snapshot_compare", SCRIPTS / "compare_snapshots.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def row(**changes):
    result = {"asin": "B0DEMO0001", "marketplace": "US", "variant": "small-1pack", "delivery_region": "US-10001",
              "currency": "USD", "price": "19.90", "price_basis": "listed-no-coupon", "observed_at": "2026-11-01T10:00:00-08:00",
              "url": "https://example.invalid/synthetic", "source_type": "synthetic", "availability": "in stock",
              "title": "Synthetic organizer", "main_image_url": "", "rating": "4.3", "review_count": "100",
              "bsr": "900", "bsr_category": "Office Products", "coupon_text": ""}
    return {**result, **changes}


def write_csv(path, records):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=records[0])
        writer.writeheader()
        writer.writerows(records)


def compare_pair(tmp_path, before, after):
    first, second = tmp_path / "old.csv", tmp_path / "new.csv"
    write_csv(first, before)
    write_csv(second, after)
    old, _ = snapshot.load(first)
    new, _ = snapshot.load(second)
    return snapshot.compare(old, new)


def test_real_price_change_keeps_evidence_and_decimal_difference(tmp_path):
    result = compare_pair(tmp_path, [row()], [row(price="17.90", observed_at="2026-11-02T10:00:00-08:00")])
    change = result[0]["changes"][0]
    assert change["difference"] == "-2.00"
    assert result[0]["before_source_type"] == "synthetic"
    assert "after_url" in result[0]


@pytest.mark.parametrize("changes", [{"currency": "CAD"}, {"price_basis": "coupon-members-only"}])
def test_changed_price_basis_is_not_reported_as_numeric_discount(tmp_path, changes):
    result = compare_pair(tmp_path, [row()], [row(price="17.90", observed_at="2026-11-02T10:00:00-08:00", **changes)])
    change = next(c for c in result[0]["changes"] if c["field"] == "price")
    assert "difference" not in change
    assert "不可比" in change["status"]


def test_missing_record_does_not_claim_delisting(tmp_path):
    result = compare_pair(tmp_path, [row()], [row(asin="B0DEMO0002", observed_at="2026-11-02T10:00:00-08:00")])
    assert {r["status"] for r in result} == {"新增观察对象", "未复查到"}


def test_category_change_blocks_bsr_difference(tmp_path):
    result = compare_pair(tmp_path, [row()], [row(bsr="10", bsr_category="Home", observed_at="2026-11-02T10:00:00-08:00")])
    change = next(c for c in result[0]["changes"] if c["field"] == "bsr")
    assert "不可比" in change["status"]
    assert "before" not in change


@pytest.mark.parametrize("changes", [{"observed_at": "2026-11-01T10:00:00"}, {"price": "NaN"},
                                     {"rating": "6"}, {"asin": "bad"}, {"variant": ""}])
def test_invalid_observation_rejected(tmp_path, changes):
    path = tmp_path / "bad.csv"
    write_csv(path, [row(**changes)])
    with pytest.raises(snapshot.SnapshotError):
        snapshot.load(path)


def test_older_snapshot_cannot_replace_newer(tmp_path):
    with pytest.raises(snapshot.SnapshotError, match="必须晚于"):
        compare_pair(tmp_path, [row()], [row(observed_at="2026-10-30T10:00:00-08:00")])


@pytest.mark.parametrize("mode", ["sales", "ads"])
def test_report_skill_cli_runs_and_refuses_overwrite(tmp_path, mode):
    names = ["sales_daily.csv"] if mode == "sales" else ["sp_search_terms_old.csv", "sp_search_terms_updated.csv"]
    sources = [ROOT / "examples" / name for name in names]
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
    output = tmp_path / "result"
    command = [sys.executable, str(SCRIPTS / "run_reports.py"), mode, "--input", *map(str, sources),
               "--store", "DEMO-STORE", "--marketplace", "US", "--currency", "USD", "--timezone", "America/Los_Angeles",
               "--data-kind", "synthetic", "--output-dir", str(output)]
    command += ["--report-date", "2026-11-01"] if mode == "sales" else ["--as-of", "2026-11-03"]
    first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=ROOT)
    assert first.returncode == 0, first.stderr
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_kind"] == "synthetic"
    assert [x["sha256"] for x in manifest["sources"]] == hashes
    book = load_workbook(next(output.glob("*.xlsx")))
    assert "范围与口径" in book.sheetnames
    if mode == "ads":
        assert manifest["rows_after_merge"] == 84
        assert manifest["pending_rows"] == 24
        assert manifest["spend_total"] == pytest.approx(1515.15)
    else:
        assert manifest["sales_total"] == pytest.approx(11283.30)
    second = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=ROOT)
    assert second.returncode != 0
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in sources] == hashes


def test_snapshot_cli_preserves_provenance(tmp_path):
    before, after = tmp_path / "before.csv", tmp_path / "after.csv"
    write_csv(before, [row()])
    write_csv(after, [row(price="18.00", observed_at="2026-11-02T10:00:00-08:00")])
    command = [sys.executable, str(SCRIPTS / "compare_snapshots.py"), "--before", str(before), "--after", str(after),
               "--output-dir", str(tmp_path / "changes")]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    data = json.loads((tmp_path / "changes" / "changes.json").read_text(encoding="utf-8"))
    assert data["sources"][0]["sha256"] == hashlib.sha256(before.read_bytes()).hexdigest()
    assert data["events"][0]["after_source_type"] == "synthetic"
