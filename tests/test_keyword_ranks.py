import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from operations import ReportError
from rank_reports import consolidate, load_observations, rank_workbook

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/keyword_ranks.csv"


def fixture_rows():
    return load_observations(EXAMPLE, "synthetic", {})[0]


def test_rank_deltas_have_correct_direction_and_missing_is_not_zero():
    history, daily = consolidate(fixture_rows())
    latest = daily.loc[(daily["asin"] == "B0DEMO0001") & (daily["rank_type"] == "organic") & (daily["date"] == "2026-11-03")]
    assert len(history) == 224
    assert latest.loc[latest["keyword"] == "desk organizer", "change_1d"].iloc[0] == 3
    assert latest.loc[latest["keyword"] == "office desk tray", "change_1d"].iloc[0] == -2
    assert pd.isna(latest.loc[latest["keyword"] == "small desk organizer", "change_1d"].iloc[0])
    assert pd.isna(latest.loc[latest["keyword"] == "desktop storage", "rank"].iloc[0])


def test_repeated_exports_do_not_create_new_history():
    rows = fixture_rows()
    single, daily = consolidate(rows)
    repeated, repeated_daily = consolidate(rows + rows)
    pd.testing.assert_frame_equal(single, repeated)
    pd.testing.assert_frame_equal(daily, repeated_daily)


def test_same_instant_conflicting_rank_rejected():
    rows = fixture_rows()
    conflict = {**rows[0], "rank": 1}
    with pytest.raises(ReportError, match="冲突"):
        consolidate(rows + [conflict])


def test_missing_calendar_day_does_not_use_last_available_observation():
    rows = [r for r in fixture_rows() if r["date"] != "2026-11-02"]
    _, daily = consolidate(rows)
    assert daily.loc[daily["date"] == "2026-11-03", "change_1d"].isna().all()


def test_changed_provider_is_separate_series():
    rows = fixture_rows()
    rows = [{**r, "provider": "Other"} if r["date"] == "2026-11-03" else r for r in rows]
    _, daily = consolidate(rows)
    assert daily.loc[daily["date"] == "2026-11-03", "change_1d"].isna().all()


@pytest.mark.parametrize("changes", [{"rank": "0"}, {"rank": "-"}, {"rank": ">306"},
                                    {"observed_at": "2026-11-03"}, {"rank_type": "aba"},
                                    {"status": "out_of_range", "rank": "", "search_limit": ""}])
def test_ambiguous_or_invalid_rank_data_rejected(changes):
    raw = pd.read_csv(EXAMPLE, dtype=str).iloc[[0]].fillna("")
    for key, value in changes.items():
        raw.loc[raw.index[0], key] = value
    with pytest.raises(ReportError):
        load_observations(Path("bad.csv"), "synthetic", {}, raw.to_csv(index=False).encode("utf-8-sig"))


def test_latest_intraday_sample_selected_without_discarding_history():
    rows = fixture_rows()
    first = rows[0]
    newer = {**first, "observed_at": "2026-10-21T12:00:00-07:00", "rank": 2,
             "_utc": first["_utc"] + pd.Timedelta(hours=2)}
    history, daily = consolidate(rows + [newer])
    assert len(history) == 225
    assert len(daily) == 224
    match = daily.loc[(daily["date"] == first["date"]) & (daily["asin"] == first["asin"]) &
                      (daily["keyword"] == first["keyword"]) & (daily["rank_type"] == first["rank_type"])]
    assert match.iloc[0]["rank"] == 2


def test_readable_workbook_has_numeric_ranks_frozen_columns_and_change_colors():
    history, daily = consolidate(fixture_rows())
    book = load_workbook(BytesIO(rank_workbook(history, daily, "synthetic")))
    matrix = book["每日排名"]
    assert matrix.freeze_panes == "D2"
    assert matrix.sheet_view.showGridLines is False
    assert isinstance(matrix["D2"].value, int)
    assert len(book["今日关注"].conditional_formatting) == 2
    assert book["今日关注"].tables


def test_daily_cli_history_round_trip_and_excel_export(tmp_path):
    script = ROOT / ".agents/skills/amazon-seller-ops/scripts/track_keyword_ranks.py"
    target = tmp_path / "first"
    command = [sys.executable, str(script), "--input", str(EXAMPLE), "--data-kind", "synthetic", "--output-dir", str(target)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    command[-1] = str(tmp_path / "second")
    command += ["--history", str(target / "rank_history.csv")]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / "second/run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["history_rows"] == 224
    assert manifest["deduplicated_rows"] == 224


def test_do_not_merge_synthetic_into_user_history():
    with pytest.raises(ReportError, match="模拟数据"):
        load_observations(EXAMPLE, "user-provided", {})
