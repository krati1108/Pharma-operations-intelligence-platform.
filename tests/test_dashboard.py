from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_every_dashboard_page_renders_without_exceptions() -> None:
    """Exercise every navigation branch with Streamlit's headless app runner."""
    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    pages = [
        "Executive Overview",
        "Inventory Risk",
        "Expiry Risk",
        "Supplier Performance",
        "Demand Forecast",
        "Replenishment Recommendations",
    ]
    app = AppTest.from_file(str(app_path), default_timeout=60).run()
    _assert_page_is_clean(app, pages[0])
    for page in pages[1:]:
        app.radio[0].set_value(page).run()
        _assert_page_is_clean(app, page)


def _assert_page_is_clean(app: AppTest, page: str) -> None:
    """Catch both uncaught failures and failures handled by the recovery UI."""
    assert not app.exception, f"Dashboard page raised an exception: {page}"
    assert not app.error, f"Dashboard page rendered an error alert: {page}"
    recovery_panels = [
        item.value
        for item in app.markdown
        if '<div class="error-panel">' in str(item.value)
    ]
    assert not recovery_panels, f"Dashboard page entered recovery mode: {page}"
