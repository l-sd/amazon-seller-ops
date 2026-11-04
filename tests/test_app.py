from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_demo_sales_and_advertising_flow():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 3
    assert "销售日报" in at.text_area[0].value
    at.sidebar.radio[1].set_value("广告报表复盘").run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 3
    assert at.metric[1].value != "0"
    at.number_input[0].set_value(50.0).run()
    assert not at.exception
    at.sidebar.radio[1].set_value("使用与口径").run()
    assert not at.exception


def test_upload_mode_waits_for_files_without_crashing():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.sidebar.radio[0].set_value("导入自己的报表").run()
    assert not at.exception
    assert not at.error
    assert any("请上传报表" in x.value for x in at.info)
