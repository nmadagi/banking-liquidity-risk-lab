"""Run the real Streamlit script headless and drive every widget."""
import warnings
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope="module")
def app():
    warnings.filterwarnings("ignore")
    script = Path(__file__).resolve().parent.parent / "app.py"
    at = AppTest.from_file(str(script), default_timeout=300)
    at.run()
    return at


def test_app_runs_without_exception(app):
    assert not app.exception, [str(e.value) for e in app.exception]


def test_headline_metrics_present(app):
    labels = [x.label for x in app.metric]
    assert any("LCR" in l for l in labels)
    assert any("Survival" in l for l in labels)


def test_all_four_tabs_exist(app):
    assert len(app.tabs) == 4


def test_every_selectbox_option_renders(app):
    for sb in app.selectbox:
        for opt in sb.options:
            sb.set_value(opt)
            app.run()
            assert not app.exception, (sb.label, opt, [str(e.value) for e in app.exception])


def test_no_em_dashes_on_screen(app):
    for md in app.markdown:
        assert "—" not in md.value
