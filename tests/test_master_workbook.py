import hashlib
from zipfile import ZipFile

import pandas as pd
import pytest
from openpyxl import load_workbook

from master_workbook import update_master
from operations import ReportError
from simulate_master import FIELDS, run_simulation


@pytest.fixture
def simulation(tmp_path):
    destination = tmp_path / "simulation"
    result = run_simulation(destination)
    import json
    profile = json.loads((destination / "profile.json").read_text(encoding="utf-8"))
    inputs = {name: destination / f"{name}.csv" for name in ("business", "ads", "pages", "ranks")}
    return destination, result, profile, inputs


def test_three_days_and_existing_formula_and_manual_log_preserved(simulation):
    directory, result, _, _ = simulation
    sheet = load_workbook(directory / result["final_workbook"])["运营总表"]
    assert len(result["days"]) == 3
    assert sheet["AF10"].data_type == "f"
    assert sheet["AK15"].value == "人工日志占位，不能覆盖"
    rows = [d["row"] for d in result["days"]]
    assert len(set(rows)) == 3
    assert sheet[f"AM{rows[-1]}"].value == 84
    assert sheet[f"AO{rows[-1]}"].value == "未采集"
    assert sheet[f"Q{rows[-1]}"].value == 250
    assert sheet[f"T{rows[-1]}"].value is None


def test_repeated_same_day_is_idempotent_and_original_unchanged(simulation):
    directory, result, profile, inputs = simulation
    source = directory / result["final_workbook"]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = directory / "repeat.xlsx"
    audit = update_master(source, output, profile, "2026-11-03", inputs)
    assert audit["changes"] == []
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    before, after = ZipFile(source), ZipFile(output)
    assert before.namelist() == after.namelist()
    assert all(before.read(n) == after.read(n) for n in before.namelist())


def test_different_same_day_value_does_not_overwrite(simulation):
    directory, result, profile, inputs = simulation
    data = pd.read_csv(inputs["business"])
    data.loc[(data["date"] == "2026-11-03"), "sales"] += 100
    path = directory / "changed_business.csv"
    data.to_csv(path, index=False)
    output = directory / "conflict.xlsx"
    with pytest.raises(ReportError, match="已有不同数据"):
        update_master(directory / result["final_workbook"], output, profile, "2026-11-03", {**inputs, "business": path})
    assert not output.exists()


def test_wrong_child_asin_rejected(simulation):
    directory, _, profile, inputs = simulation
    data = pd.read_csv(inputs["business"])
    data.loc[0, "child_asin"] = "B0OTHER001"
    path = directory / "wrong.csv"
    data.to_csv(path, index=False)
    with pytest.raises(ReportError, match="未确认归属"):
        update_master(directory / "synthetic_template.xlsx", directory / "bad.xlsx", profile, "2026-11-01", {**inputs, "business": path})


def test_missing_date_cannot_create_empty_daily_record(simulation):
    directory, _, profile, inputs = simulation
    with pytest.raises(ReportError, match="没有可用"):
        update_master(directory / "synthetic_template.xlsx", directory / "empty.xlsx", profile, "2026-11-20", inputs)


def test_unknown_keyword_not_added_to_master(simulation):
    directory, _, profile, inputs = simulation
    ranks = pd.read_csv(inputs["ranks"])
    ranks["keyword"] = "not in master"
    ranks = ranks.drop_duplicates(["observed_at"])
    path = directory / "unknown-ranks.csv"
    ranks.to_csv(path, index=False)
    result = update_master(directory / "synthetic_template.xlsx", directory / "unknown.xlsx", profile,
                           "2026-11-01", {**inputs, "ranks": path})
    assert result["unmatched_rank_words"] == ["not in master"]
    sheet = load_workbook(directory / "unknown.xlsx")["运营总表"]
    assert sheet[f"AM{result['row']}"].value is None


def test_unsafe_organic_derivation_mapping_rejected(simulation):
    directory, _, profile, inputs = simulation
    profile["field_columns"] = {**FIELDS, "organic_orders": "T"}
    with pytest.raises(ReportError):
        update_master(directory / "synthetic_template.xlsx", directory / "unsafe.xlsx", profile, "2026-11-01", inputs)


def test_other_package_parts_and_styles_survive(simulation):
    directory, result, _, _ = simulation
    source = directory / "synthetic_template.xlsx"
    output = directory / result["final_workbook"]
    before, after = ZipFile(source), ZipFile(output)
    member = result["days"][0]["only_modified_package_part"]
    assert all(before.read(n) == after.read(n) for n in before.namelist() if n != member)
    a, b = load_workbook(source), load_workbook(output)
    assert a["运营总表"]["AM11"].style_id == b["运营总表"]["AM11"].style_id
    assert a["后台广告报告"]["A1"].value == b["后台广告报告"]["A1"].value
