"""Streamlit application for pharmaceutical operations decision support."""

from __future__ import annotations

import html
import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DATABASE_PATH, SIMULATION_DATE
from src.data_pipeline import run_pipeline
from src.database import query_dataframe
from src.demand_forecasting import (
    forecast_weekly_demand,
    get_demand_history,
)
from src.expiry_analysis import get_expiry_risk, get_expiry_summary
from src.inventory_analysis import (
    get_inventory_health,
    get_replenishment_recommendations,
    get_warehouse_summary,
)
from src.supplier_analysis import (
    get_supplier_order_detail,
    get_supplier_performance,
)

LOGGER = logging.getLogger(__name__)

st.set_page_config(
    page_title="Pharma Operations Intelligence",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = {
    "ink": "#2B1B2E",
    "plum": "#6B2D5C",
    "berry": "#A13D63",
    "rose": "#D46A7E",
    "amber": "#E0A458",
    "terracotta": "#D56A4A",
    "red": "#B23A48",
    "sage": "#6A8E5B",
    "slate": "#6B5B67",
    "canvas": "#FAF6F1",
}

RISK_COLORS = {
    "Critical": COLORS["red"],
    "High": COLORS["terracotta"],
    "Watch": COLORS["amber"],
    "Healthy": COLORS["sage"],
}

DASHBOARD_ERRORS = (
    OSError,
    sqlite3.Error,
    ValueError,
    KeyError,
    TypeError,
    ArithmeticError,
)

st.markdown(
    """
    <style>
    :root {
        --ink: #2B1B2E;
        --muted: #6B5B67;
        --accent: #A13D63;
        --amber: #E0A458;
        --canvas: #FAF6F1;
        --card: #FFFFFF;
        --border: #E7D8DE;
    }
    .stApp {
        background:
            radial-gradient(circle at 88% 0%, rgba(224, 164, 88, .15), transparent 24rem),
            linear-gradient(180deg, #FFFDFC 0%, var(--canvas) 100%);
    }
    .block-container {
        max-width: 1500px;
        padding-top: 1.35rem;
        padding-bottom: 3rem;
    }
    .hero-panel {
        display: flex;
        align-items: center;
        gap: 1.1rem;
        margin-bottom: 1.35rem;
        padding: 1.35rem 1.55rem;
        color: #FFFFFF;
        background: linear-gradient(115deg, #2B1B2E 0%, #5B274B 58%, #8A463D 100%);
        border: 1px solid rgba(255,255,255,.15);
        border-radius: 18px;
        box-shadow: 0 14px 35px rgba(64, 29, 49, .18);
    }
    .hero-icon {
        display: grid;
        place-items: center;
        min-width: 3.2rem;
        height: 3.2rem;
        font-size: 1.5rem;
        background: rgba(255,255,255,.12);
        border: 1px solid rgba(255,255,255,.22);
        border-radius: 14px;
    }
    .hero-eyebrow {
        margin-bottom: .22rem;
        color: #F4C98B;
        font-size: .70rem;
        font-weight: 800;
        letter-spacing: .14em;
    }
    .hero-panel h1 {
        margin: 0;
        color: #FFFFFF;
        font-size: clamp(1.65rem, 3vw, 2.25rem);
        line-height: 1.15;
    }
    .hero-panel p {margin: .4rem 0 0; color: #F1E3E9; font-size: .96rem;}
    [data-testid="stMetric"] {
        min-height: 116px;
        padding: .95rem 1.05rem;
        background: linear-gradient(145deg, #FFFFFF 0%, #FFF9F5 100%);
        border: 1px solid var(--border);
        border-top: 4px solid var(--accent);
        border-radius: 14px;
        box-shadow: 0 7px 20px rgba(84, 43, 65, .08);
        transition: transform .18s ease, box-shadow .18s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 11px 25px rgba(84, 43, 65, .13);
    }
    [data-testid="stMetricLabel"] p {
        color: var(--muted) !important;
        font-size: .76rem;
        font-weight: 750;
        letter-spacing: .015em;
    }
    [data-testid="stMetricValue"] {
        color: var(--ink);
        font-size: 1.55rem;
        font-weight: 800;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(170deg, #21151F 0%, #46233C 57%, #67352E 130%);
        border-right: 1px solid rgba(255,255,255,.08);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #E7D7DE;
    }
    .sidebar-brand {display: flex; align-items: center; gap: .75rem; margin: .35rem 0 .9rem;}
    .sidebar-logo {
        display: grid;
        place-items: center;
        width: 2.8rem;
        height: 2.8rem;
        color: #3B2130;
        background: linear-gradient(135deg, #F5D39D, #E0A458);
        border-radius: 12px;
        font-size: 1.05rem;
        font-weight: 900;
        box-shadow: 0 8px 18px rgba(0,0,0,.18);
    }
    .sidebar-brand strong {display: block; color: #FFFFFF; font-size: 1rem; line-height: 1.15;}
    .sidebar-brand span {color: #D5BBC7; font-size: .72rem;}
    .date-badge {
        display: inline-flex;
        margin: .15rem 0 1.1rem;
        padding: .38rem .65rem;
        color: #FFF0D8;
        background: rgba(224, 164, 88, .13);
        border: 1px solid rgba(244, 201, 139, .28);
        border-radius: 999px;
        font-size: .73rem;
        font-weight: 700;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        margin: .18rem 0;
        padding: .52rem .62rem;
        border-radius: 9px;
        transition: background .16s ease;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label p {color: #E7D7DE !important;}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {background: rgba(255,255,255,.07);}
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(90deg, rgba(224,164,88,.25), rgba(161,61,99,.08));
        box-shadow: inset 3px 0 0 #E0A458;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
        color: #FFFFFF !important;
        font-weight: 750;
    }
    [data-testid="stSidebar"] .stButton button {
        width: 100%;
        color: #FFF7EA;
        background: rgba(224,164,88,.11);
        border: 1px solid rgba(244,201,139,.34);
    }
    [data-testid="stSidebar"] .stButton button:hover {
        color: #2B1B2E;
        background: #F4C98B;
        border-color: #F4C98B;
    }
    h2, h3 {color: var(--ink); letter-spacing: -.015em;}
    [data-testid="stDataFrame"] {
        overflow: hidden;
        border: 1px solid var(--border);
        border-radius: 12px;
        box-shadow: 0 5px 16px rgba(84, 43, 65, .06);
    }
    div[data-baseweb="select"] > div {
        background: #FFFFFF;
        border-color: #D7BFC9;
        border-radius: 9px;
    }
    .status-note {
        margin: .5rem 0 1rem;
        padding: .9rem 1rem;
        color: #63334F;
        background: linear-gradient(90deg, #F9E8EE, #FFF6EA);
        border: 1px solid #E8C5D2;
        border-left: 4px solid var(--accent);
        border-radius: 10px;
    }
    .error-panel {
        padding: 1.1rem 1.2rem;
        color: #711D2A;
        background: #FFF1F2;
        border: 1px solid #FECDD3;
        border-left: 5px solid #C2414B;
        border-radius: 12px;
    }
    .error-panel h3 {margin: 0 0 .3rem; color: #881D2D;}
    .error-panel p {margin: 0; color: #7A3440;}
    [data-testid="stAlert"] {border-radius: 11px;}
    .command-strip {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .75rem;
        margin: .25rem 0 1.15rem;
    }
    .command-card {
        position: relative;
        overflow: hidden;
        min-height: 94px;
        padding: .9rem 1rem .85rem 1.1rem;
        background: rgba(255,255,255,.88);
        border: 1px solid var(--border);
        border-radius: 13px;
        box-shadow: 0 5px 16px rgba(84,43,65,.06);
    }
    .command-card::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 4px;
        background: var(--accent);
    }
    .command-card.good::before {background: #6A8E5B;}
    .command-card.watch::before {background: #E0A458;}
    .command-card.risk::before {background: #B23A48;}
    .command-card.info::before {background: #6B2D5C;}
    .command-label {
        color: var(--muted);
        font-size: .68rem;
        font-weight: 800;
        letter-spacing: .085em;
        text-transform: uppercase;
    }
    .command-value {margin-top: .22rem; color: var(--ink); font-size: 1.18rem; font-weight: 850;}
    .command-detail {margin-top: .15rem; color: #836E78; font-size: .73rem;}
    .section-heading {display: flex; align-items: flex-end; justify-content: space-between; margin: 1.15rem 0 .7rem;}
    .section-heading h3 {margin: 0; font-size: 1.12rem;}
    .section-heading p {margin: .18rem 0 0; color: var(--muted); font-size: .82rem;}
    .section-kicker {color: var(--accent); font-size: .65rem; font-weight: 850; letter-spacing: .12em;}
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255,255,255,.70);
        border-color: var(--border) !important;
        border-radius: 14px !important;
        box-shadow: 0 5px 16px rgba(84,43,65,.045);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: .3rem;
        padding: .28rem;
        background: #F1E5E1;
        border-radius: 11px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 2.45rem;
        padding: 0 1rem;
        color: #715C68;
        background: transparent;
        border-radius: 8px;
    }
    .stTabs [aria-selected="true"] {
        color: #FFFFFF !important;
        background: linear-gradient(100deg, #6B2D5C, #A13D63) !important;
        box-shadow: 0 4px 12px rgba(107,45,92,.20);
    }
    .stTabs [data-baseweb="tab-highlight"] {display: none;}
    .app-footer {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        margin-top: 2.25rem;
        padding-top: 1rem;
        color: #816D77;
        border-top: 1px solid #E7D8DE;
        font-size: .73rem;
    }
    .app-footer strong {color: #5B304B;}
    .hero-meta {margin-left: auto; text-align: right; white-space: nowrap;}
    .hero-meta span {
        display: inline-flex;
        padding: .35rem .62rem;
        color: #3B2130;
        background: #F4C98B;
        border-radius: 999px;
        font-size: .66rem;
        font-weight: 850;
        letter-spacing: .08em;
    }
    .hero-meta small {display: block; margin-top: .38rem; color: #E7CFD9; font-size: .68rem;}
    @media (max-width: 900px) {
        .command-strip {grid-template-columns: repeat(2, minmax(0, 1fr));}
        .hero-meta {display: none;}
    }
    @media (max-width: 620px) {
        .command-strip {grid-template-columns: 1fr;}
        .hero-panel {align-items: flex-start; padding: 1rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def database_is_ready() -> bool:
    """Check that the local database includes the current dashboard contract."""
    if not DATABASE_PATH.exists():
        return False
    with sqlite3.connect(DATABASE_PATH) as connection:
        objects = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        required_objects = {
            "simulation_config",
            "v_executive_kpis",
            "v_inventory_health",
            "v_expiry_risk",
            "v_supplier_performance",
        }
        inventory_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(v_inventory_health)")
        }
        return required_objects.issubset(objects) and {
            "inventory_position",
            "on_order_quantity",
            "expired_inventory_quantity",
        }.issubset(inventory_columns)


def show_recovery_error(title: str, message: str, exc: Exception, key: str) -> None:
    """Render an actionable error state without exposing a raw traceback."""
    st.markdown(
        f"""
        <div class="error-panel">
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(message)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Technical details"):
        st.code(f"{type(exc).__name__}: {exc}")
        st.caption("If rebuilding does not help, run `python -m src.data_pipeline` in the terminal.")
    if st.button("Rebuild analytics database", key=f"rebuild-{key}", type="primary"):
        try:
            with st.spinner("Rebuilding validated synthetic data and SQLite views…"):
                run_pipeline()
                st.cache_data.clear()
            st.success("Database rebuilt successfully. Reloading the dashboard…")
            st.rerun()
        except DASHBOARD_ERRORS as rebuild_error:
            LOGGER.exception("Dashboard database rebuild failed")
            st.error(f"Rebuild failed: {type(rebuild_error).__name__}: {rebuild_error}")


def ensure_database() -> None:
    """Bootstrap missing/stale data and show a recoverable state on failure."""
    try:
        if not database_is_ready():
            with st.spinner("Preparing the pharmaceutical operations database…"):
                run_pipeline()
    except (OSError, sqlite3.Error, ValueError) as exc:
        LOGGER.exception("Dashboard database initialization failed")
        show_recovery_error(
            "The analytics database could not be prepared",
            "The local data may be missing, stale, or unreadable. Rebuild it to restore the dashboard.",
            exc,
            "startup",
        )
        st.stop()


@st.cache_data(show_spinner=False)
def read_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    return query_dataframe(query, params=params)


def money(value: float) -> str:
    return f"${value:,.0f}"


def percent(value: float) -> str:
    return f"{value:,.1f}%"


def style_figure(figure: go.Figure) -> go.Figure:
    """Apply one accessible visual system to every Plotly chart."""
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0)",
        font={"color": COLORS["ink"], "family": "Arial, sans-serif", "size": 12},
        title_font={"color": COLORS["ink"], "size": 17},
        margin={"l": 18, "r": 18, "t": 62, "b": 20},
        hoverlabel={"bgcolor": COLORS["ink"], "font_color": "#FFFFFF"},
        legend={"bgcolor": "rgba(255,255,255,.75)"},
    )
    figure.update_xaxes(gridcolor="#E9DDE2", zerolinecolor="#D9C6CE")
    figure.update_yaxes(gridcolor="#E9DDE2", zerolinecolor="#D9C6CE")
    return figure


def page_header(title: str, caption: str) -> None:
    icons = {
        "Executive Overview": "⌁",
        "Inventory Risk": "▦",
        "Expiry Risk": "◷",
        "Supplier Performance": "◇",
        "Demand Forecast": "↗",
        "Replenishment Recommendations": "⇄",
    }
    st.markdown(
        f"""
        <div class="hero-panel">
            <div class="hero-icon">{icons.get(title, "Rx")}</div>
            <div>
                <div class="hero-eyebrow">PHARMA SUPPLY CHAIN CONTROL TOWER</div>
                <h1>{html.escape(title)}</h1>
                <p>{html.escape(caption)}</p>
            </div>
            <div class="hero-meta">
                <span>SIMULATED OPERATIONS</span>
                <small>Business date · {SIMULATION_DATE}</small>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, caption: str, kicker: str = "DECISION VIEW") -> None:
    """Create a compact visual divider for analytical sections."""
    st.markdown(
        f"""
        <div class="section-heading">
            <div>
                <div class="section-kicker">{html.escape(kicker)}</div>
                <h3>{html.escape(title)}</h3>
                <p>{html.escape(caption)}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def command_strip(items: list[tuple[str, str, str, str]]) -> None:
    """Render a responsive operational status strip above detailed analysis."""
    cards = []
    allowed_tones = {"good", "watch", "risk", "info"}
    for label, value, detail, tone in items:
        safe_tone = tone if tone in allowed_tones else "info"
        cards.append(
            f'<div class="command-card {safe_tone}">'
            f'<div class="command-label">{html.escape(label)}</div>'
            f'<div class="command-value">{html.escape(value)}</div>'
            f'<div class="command-detail">{html.escape(detail)}</div>'
            "</div>"
        )
    st.markdown(
        f'<div class="command-strip">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def page_footer() -> None:
    st.markdown(
        f"""
        <div class="app-footer">
            <span><strong>Pharma Operations Intelligence Platform</strong> · Decision support prototype</span>
            <span>Synthetic data · Business date {SIMULATION_DATE}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_executive_overview() -> None:
    page_header(
        "Executive Overview",
        "Network-level commercial, inventory, service, and supply-risk performance.",
    )
    kpi = read_sql("SELECT * FROM v_executive_kpis").iloc[0]
    current_sales = read_sql(
        """
        WITH latest AS (SELECT MAX(week_start) AS max_week FROM weekly_sales)
        SELECT
            SUM(demand_units) AS demand_units,
            SUM(units_sold) AS units_sold,
            ROUND(100.0 * SUM(units_sold) / SUM(demand_units), 2) AS service_level_pct
        FROM weekly_sales, latest
        WHERE week_start > date(max_week, '-84 days')
        """
    ).iloc[0]

    sales = read_sql(
        """
        SELECT week_start, SUM(revenue) AS revenue, SUM(units_sold) AS units_sold
        FROM weekly_sales GROUP BY week_start ORDER BY week_start
        """
    )
    sales["week_start"] = pd.to_datetime(sales["week_start"])
    inventory = get_warehouse_summary()
    therapy = read_sql(
        """
        SELECT
            p.therapeutic_area,
            ROUND(SUM(ws.revenue), 2) AS revenue,
            SUM(ws.units_sold) AS units_sold,
            ROUND(100.0 * SUM(ws.units_sold) / SUM(ws.demand_units), 2) AS service_level_pct
        FROM weekly_sales ws
        JOIN products p ON p.product_id = ws.product_id
        GROUP BY p.therapeutic_area
        ORDER BY revenue DESC
        """
    )

    command_strip(
        [
            (
                "Service pulse",
                percent(current_sales.service_level_pct),
                "Trailing 12-week fulfillment",
                "good" if current_sales.service_level_pct >= 97 else "watch",
            ),
            (
                "Critical positions",
                f"{int(kpi.critical_stockout_skus):,}",
                "SKU-locations below safety stock",
                "risk",
            ),
            (
                "Replenishment queue",
                f"{int(kpi.replenishment_flags):,}",
                "Net of confirmed open POs",
                "watch",
            ),
            (
                "Expiry exposure",
                money(kpi.expiry_value_at_risk_180_days),
                "Cost value inside 180 days",
                "risk",
            ),
        ]
    )

    headline = st.columns([1.15, 1, 1])
    headline[0].metric("Total Revenue · 104 weeks", money(kpi.total_revenue))
    headline[1].metric("Units Sold", f"{int(kpi.units_sold):,}")
    headline[2].metric("Usable Inventory Value", money(kpi.inventory_value))

    network_tab, portfolio_tab, kpi_tab = st.tabs(
        ["◉ Network pulse", "◆ Therapy portfolio", "▤ KPI detail"]
    )
    with network_tab:
        section_header(
            "Network movement",
            "Commercial momentum and inventory concentration across the distribution network.",
        )
        left, right = st.columns([1.65, 1], gap="large")
        with left:
            fig = px.area(
                sales,
                x="week_start",
                y="revenue",
                color_discrete_sequence=[COLORS["berry"]],
                title="Weekly revenue trajectory",
            )
            fig.update_layout(yaxis_tickprefix="$", hovermode="x unified", showlegend=False)
            st.plotly_chart(style_figure(fig), width="stretch")
        with right:
            fig = px.bar(
                inventory,
                x="inventory_value",
                y="warehouse_name",
                orientation="h",
                color="critical_skus",
                color_continuous_scale=["#F3D8E2", COLORS["amber"], COLORS["red"]],
                title="Inventory investment by DC",
            )
            fig.update_layout(
                yaxis_title=None,
                xaxis_tickprefix="$",
                coloraxis_colorbar_title="Critical",
            )
            st.plotly_chart(style_figure(fig), width="stretch")

    with portfolio_tab:
        section_header(
            "Therapeutic portfolio",
            "Revenue contribution and simulated service performance by therapeutic area.",
        )
        visual, detail = st.columns([1.05, 1], gap="large")
        with visual:
            therapy_chart = px.bar(
                therapy.sort_values("revenue"),
                x="revenue",
                y="therapeutic_area",
                orientation="h",
                color="service_level_pct",
                color_continuous_scale=[COLORS["red"], COLORS["amber"], COLORS["sage"]],
                title="Portfolio revenue and service level",
            )
            therapy_chart.update_layout(
                xaxis_tickprefix="$",
                yaxis_title=None,
                coloraxis_colorbar_title="Service %",
            )
            st.plotly_chart(style_figure(therapy_chart), width="stretch")
        with detail:
            st.dataframe(
                therapy,
                width="stretch",
                hide_index=True,
                column_config={
                    "therapeutic_area": "Therapeutic Area",
                    "revenue": st.column_config.NumberColumn("Revenue", format="$%.2f"),
                    "units_sold": st.column_config.NumberColumn("Units Sold", format="%,d"),
                    "service_level_pct": st.column_config.ProgressColumn(
                        "Service Level", min_value=90, max_value=100, format="%.2f%%"
                    ),
                },
            )

    with kpi_tab:
        section_header(
            "Operating guardrails",
            "Coverage, shelf-life, and supplier indicators used to prioritize intervention.",
        )
        detail_metrics = st.columns(4)
        detail_metrics[0].metric("Network Weeks of Supply", f"{kpi.network_weeks_of_supply:.1f}")
        detail_metrics[1].metric("Expiring ≤90 Days", f"{int(kpi.units_expiring_90_days):,} units")
        detail_metrics[2].metric(
            "Supplier On-Time Delivery", percent(kpi.supplier_on_time_delivery_pct)
        )
        detail_metrics[3].metric(
            "Supplier Acceptance / Quality", percent(kpi.supplier_acceptance_quality_pct)
        )
        st.markdown(
            '<div class="status-note"><b>Executive interpretation:</b> network-wide averages are '
            "directional. Planner action should be driven by the product-location and batch queues "
            "on the dedicated risk pages.</div>",
            unsafe_allow_html=True,
        )


def show_inventory_risk() -> None:
    page_header(
        "Inventory Risk",
        "Position-level stockout exposure, coverage, and working-capital visibility.",
    )
    base = get_inventory_health()
    warehouses = {"All distribution centers": None} | dict(
        zip(base["warehouse_name"].drop_duplicates(), base["warehouse_id"].drop_duplicates())
    )
    therapy_options = ["All therapeutic areas"] + sorted(base["therapeutic_area"].unique())
    with st.container(border=True):
        section_header(
            "Scope controls",
            "Focus the risk view without changing the underlying inventory policy.",
            "FILTERS",
        )
        col1, col2, col3 = st.columns([1, 1, 1.15])
        warehouse_label = col1.selectbox("Distribution center", list(warehouses))
        therapy = col2.selectbox("Therapeutic area", therapy_options)
        col3.markdown(
            '<div class="status-note"><b>Risk rule:</b> Critical means usable stock is at or below '
            "safety stock. Open POs reduce replenishment quantity, not immediate stockout risk.</div>",
            unsafe_allow_html=True,
        )
    inventory = get_inventory_health(
        warehouse_id=warehouses[warehouse_label],
        therapeutic_area=None if therapy == "All therapeutic areas" else therapy,
    )

    critical_count = int((inventory.stockout_risk == "Critical").sum())
    network_wos = inventory.inventory_quantity.sum() / inventory.avg_weekly_demand.sum()
    command_strip(
        [
            ("Positions in scope", f"{len(inventory):,}", warehouse_label, "info"),
            ("Critical", f"{critical_count:,}", "At or below safety stock", "risk"),
            (
                "Net replenishment",
                f"{int(inventory.replenishment_flag.sum()):,}",
                "Positions requiring a new order",
                "watch",
            ),
            ("Weighted coverage", f"{network_wos:.1f} weeks", "Usable stock only", "good"),
        ]
    )

    coverage_tab, queue_tab, warehouse_tab = st.tabs(
        ["◎ Coverage map", "⚑ Action queue", "▦ Warehouse lens"]
    )
    with coverage_tab:
        section_header(
            "Coverage and capital exposure",
            "Bubble size represents recent demand; the six-week line marks the watch threshold.",
        )
        left, right = st.columns([1.55, 1], gap="large")
        with left:
            fig = px.scatter(
                inventory,
                x="weeks_of_supply",
                y="inventory_value",
                size="avg_weekly_demand",
                color="stockout_risk",
                hover_name="product_name",
                hover_data=[
                    "warehouse_name",
                    "inventory_quantity",
                    "on_order_quantity",
                    "inventory_position",
                    "reorder_point",
                ],
                color_discrete_map=RISK_COLORS,
                title="Coverage vs. inventory investment",
            )
            fig.add_vline(x=6, line_dash="dash", line_color=COLORS["slate"])
            fig.update_layout(yaxis_tickprefix="$", legend_title=None)
            st.plotly_chart(style_figure(fig), width="stretch")
        with right:
            risk_counts = inventory.groupby("stockout_risk", as_index=False).size()
            fig = px.pie(
                risk_counts,
                values="size",
                names="stockout_risk",
                hole=0.64,
                title="Position risk mix",
                color="stockout_risk",
                color_discrete_map=RISK_COLORS,
            )
            st.plotly_chart(style_figure(fig), width="stretch")

    with queue_tab:
        section_header(
            "Prioritized inventory queue",
            "Positions are ordered by replenishment need and lowest weeks of supply.",
        )
        st.dataframe(
            inventory[
                [
                    "product_id",
                    "product_name",
                    "warehouse_name",
                    "inventory_quantity",
                    "expired_inventory_quantity",
                    "on_order_quantity",
                    "inventory_position",
                    "safety_stock",
                    "reorder_point",
                    "avg_weekly_demand",
                    "weeks_of_supply",
                    "stockout_risk",
                    "inventory_value",
                ]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "inventory_value": st.column_config.NumberColumn("Inventory Value", format="$%.2f"),
                "weeks_of_supply": st.column_config.NumberColumn("Weeks of Supply", format="%.1f"),
                "avg_weekly_demand": st.column_config.NumberColumn(
                    "Avg Weekly Demand", format="%.1f"
                ),
            },
        )

    with warehouse_tab:
        section_header(
            "Distribution-center comparison",
            "Compare usable inventory, weighted coverage, and action volume by warehouse.",
        )
        warehouse_summary = get_warehouse_summary()
        warehouse_chart = px.bar(
            warehouse_summary.sort_values("inventory_value"),
            x="inventory_value",
            y="warehouse_name",
            orientation="h",
            color="replenishment_flags",
            color_continuous_scale=["#F3D8E2", COLORS["amber"], COLORS["red"]],
            title="Inventory value and replenishment burden",
        )
        warehouse_chart.update_layout(
            xaxis_tickprefix="$",
            yaxis_title=None,
            coloraxis_colorbar_title="Flags",
        )
        st.plotly_chart(style_figure(warehouse_chart), width="stretch")
        st.dataframe(warehouse_summary, width="stretch", hide_index=True)


def show_expiry_risk() -> None:
    page_header(
        "Expiry Risk",
        "Batch-level shelf-life exposure for FEFO allocation, transfer, and disposition decisions.",
    )
    batches = get_expiry_risk(include_long_dated=False)
    summary = get_expiry_summary()
    expiring_90 = batches.loc[batches.days_to_expiry <= 90]
    expiring_180 = batches.loc[batches.days_to_expiry <= 180]
    action_frame = batches.copy()
    action_frame["recommended_action"] = action_frame["days_to_expiry"].apply(
        lambda days: "Quarantine / disposition"
        if days < 0
        else "Prioritize allocation / transfer"
        if days <= 90
        else "Monitor weekly"
        if days <= 180
        else "Monitor monthly"
    )

    command_strip(
        [
            ("Urgent batches", f"{len(expiring_90):,}", "Expired or inside 90 days", "risk"),
            (
                "Units ≤90 days",
                f"{int(expiring_90.inventory_quantity.sum()):,}",
                "Priority allocation population",
                "risk",
            ),
            (
                "Units ≤180 days",
                f"{int(expiring_180.inventory_quantity.sum()):,}",
                "Weekly monitoring horizon",
                "watch",
            ),
            (
                "Value at risk",
                money(expiring_180.inventory_value_at_risk.sum()),
                "Cost exposure inside 180 days",
                "info",
            ),
        ]
    )

    exposure_tab, queue_tab, playbook_tab = st.tabs(
        ["◷ Exposure map", "⚑ FEFO action queue", "▤ Response playbook"]
    )
    with exposure_tab:
        section_header(
            "Shelf-life exposure",
            "Value concentration by time horizon and the batches driving the largest exposure.",
        )
        left, right = st.columns([1.05, 1.7], gap="large")
        with left:
            fig = px.bar(
                summary,
                x="expiry_bucket",
                y="inventory_value_at_risk",
                color="expiry_bucket",
                category_orders={
                    "expiry_bucket": [
                        "Expired",
                        "0-90 days",
                        "91-180 days",
                        "181-365 days",
                        "Over 365 days",
                    ]
                },
                color_discrete_sequence=[
                    "#8F2635",
                    COLORS["red"],
                    COLORS["amber"],
                    COLORS["plum"],
                    COLORS["sage"],
                ],
                title="Value by shelf-life bucket",
            )
            fig.update_layout(
                showlegend=False,
                xaxis_title=None,
                yaxis_tickprefix="$",
                xaxis_tickangle=-20,
            )
            st.plotly_chart(style_figure(fig), width="stretch")
        with right:
            top = batches.nlargest(20, "inventory_value_at_risk").sort_values(
                "inventory_value_at_risk"
            )
            fig = px.bar(
                top,
                x="inventory_value_at_risk",
                y="batch_number",
                orientation="h",
                color="expiry_bucket",
                hover_data=["product_name", "warehouse_name", "expiry_date", "inventory_quantity"],
                title="Highest-value at-risk batches",
                color_discrete_map={
                    "Expired": "#8F2635",
                    "0-90 days": COLORS["red"],
                    "91-180 days": COLORS["amber"],
                    "181-365 days": COLORS["plum"],
                },
            )
            fig.update_layout(xaxis_tickprefix="$", legend_title=None)
            st.plotly_chart(style_figure(fig), width="stretch")

    with queue_tab:
        section_header(
            "First-expire, first-out queue",
            "Batch-level actions ordered by remaining shelf life and exposed value.",
        )
        st.dataframe(
            action_frame[
                [
                    "batch_number",
                    "product_name",
                    "warehouse_name",
                    "expiry_date",
                    "days_to_expiry",
                    "inventory_quantity",
                    "inventory_value_at_risk",
                    "recommended_action",
                ]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "inventory_value_at_risk": st.column_config.NumberColumn(
                    "Value at Risk", format="$%.2f"
                )
            },
        )

    with playbook_tab:
        section_header(
            "Shelf-life response playbook",
            "Suggested operating cadence by expiry horizon; decisions remain subject to quality policy.",
        )
        command_strip(
            [
                ("Expired", "Quarantine", "Block allocation and assess disposition", "risk"),
                ("0–90 days", "Act now", "Transfer, return, or prioritize demand", "risk"),
                ("91–180 days", "Monitor weekly", "Review demand coverage and redistribution", "watch"),
                ("181–365 days", "Monitor monthly", "Maintain FEFO allocation sequence", "good"),
            ]
        )
        st.dataframe(summary, width="stretch", hide_index=True)


def show_supplier_performance() -> None:
    page_header(
        "Supplier Performance",
        "Weighted delivery, fill-rate, quality-acceptance, and lead-time scorecards.",
    )
    suppliers = get_supplier_performance()
    preferred_count = int((suppliers.performance_tier == "Preferred").sum())
    action_count = int((suppliers.performance_tier == "Needs Action").sum())
    command_strip(
        [
            (
                "On-time delivery",
                percent(suppliers.on_time_delivery_pct.mean()),
                "Average across supplier scorecards",
                "good" if suppliers.on_time_delivery_pct.mean() >= 92 else "watch",
            ),
            (
                "Accepted quality",
                percent(suppliers.acceptance_quality_pct.mean()),
                "Accepted units divided by received",
                "good",
            ),
            (
                "Preferred suppliers",
                f"{preferred_count} of {len(suppliers)}",
                "Composite score above 92",
                "good",
            ),
            (
                "Needs action",
                f"{action_count}",
                "Composite score below 85",
                "risk" if action_count else "good",
            ),
        ]
    )

    matrix_tab, scorecard_tab, orders_tab = st.tabs(
        ["◇ Performance matrix", "▤ Supplier scorecard", "⌕ Purchase-order explorer"]
    )
    with matrix_tab:
        section_header(
            "Reliability and quality matrix",
            "Bubble size represents total purchase-order value; tier reflects the weighted score.",
        )
        fig = px.scatter(
            suppliers,
            x="on_time_delivery_pct",
            y="acceptance_quality_pct",
            size="total_po_value",
            color="performance_tier",
            text="supplier_name",
            hover_data=["fill_rate_pct", "actual_lead_time_days", "performance_score"],
            color_discrete_map={
                "Preferred": COLORS["sage"],
                "Monitor": COLORS["amber"],
                "Needs Action": COLORS["red"],
            },
            title="Delivery reliability vs. accepted quality",
        )
        fig.update_traces(textposition="top center")
        fig.update_layout(xaxis_ticksuffix="%", yaxis_ticksuffix="%", legend_title=None)
        st.plotly_chart(style_figure(fig), width="stretch")

    with scorecard_tab:
        section_header(
            "Supplier scorecard",
            "Ranked performance with weighted delivery, quality, and fill-rate evidence.",
        )
        score_view, spend_view = st.columns([1.55, 1], gap="large")
        with score_view:
            st.dataframe(
                suppliers,
                width="stretch",
                hide_index=True,
                column_config={
                    "total_po_value": st.column_config.NumberColumn(
                        "Total PO Value", format="$%.2f"
                    ),
                    "performance_score": st.column_config.ProgressColumn(
                        "Score", min_value=0, max_value=100, format="%.1f"
                    ),
                },
            )
        with spend_view:
            spend_chart = px.bar(
                suppliers.sort_values("total_po_value"),
                x="total_po_value",
                y="supplier_name",
                orientation="h",
                color="performance_tier",
                color_discrete_map={
                    "Preferred": COLORS["sage"],
                    "Monitor": COLORS["amber"],
                    "Needs Action": COLORS["red"],
                },
                title="PO value by supplier",
            )
            spend_chart.update_layout(xaxis_tickprefix="$", yaxis_title=None, legend_title=None)
            st.plotly_chart(style_figure(spend_chart), width="stretch")

    with orders_tab:
        section_header(
            "Purchase-order evidence",
            "Inspect delivery dates, fill quantities, and acceptance behind each supplier score.",
        )
        with st.container(border=True):
            selected_name = st.selectbox(
                "Select supplier to inspect", suppliers["supplier_name"]
            )
        selected_id = suppliers.loc[
            suppliers.supplier_name == selected_name, "supplier_id"
        ].iloc[0]
        st.dataframe(get_supplier_order_detail(selected_id), width="stretch", hide_index=True)


def show_demand_forecast() -> None:
    page_header(
        "Demand Forecast",
        "Validated seasonal-trend forecasts at network, product, warehouse, or SKU-location level.",
    )
    products = read_sql("SELECT product_id, product_name FROM products ORDER BY product_name")
    warehouses = read_sql("SELECT warehouse_id, warehouse_name FROM warehouses ORDER BY warehouse_name")
    product_options = {"All products": None} | dict(zip(products.product_name, products.product_id))
    warehouse_options = {"All distribution centers": None} | dict(
        zip(warehouses.warehouse_name, warehouses.warehouse_id)
    )
    with st.container(border=True):
        section_header(
            "Forecast controls",
            "Select the aggregation level used for model validation and the future horizon.",
            "MODEL SCOPE",
        )
        col1, col2 = st.columns(2)
        product_label = col1.selectbox("Product", list(product_options))
        warehouse_label = col2.selectbox("Distribution center", list(warehouse_options))
    history = get_demand_history(
        product_id=product_options[product_label],
        warehouse_id=warehouse_options[warehouse_label],
    )
    result = forecast_weekly_demand(history)
    last_actual = float(result.history.actual_demand.iloc[-1])
    forecast_total = float(result.future.forecast_demand.sum())
    baseline_improvement = (
        100 * (result.baseline_mae - result.mae) / result.baseline_mae
        if result.baseline_mae > 0
        else None
    )
    command_strip(
        [
            (
                "12-week demand",
                f"{forecast_total:,.0f} units",
                f"Average {forecast_total / 12:,.1f} per week",
                "info",
            ),
            ("Validation MAE", f"{result.mae:,.1f}", "Absolute units per week", "good"),
            ("Validation MAPE", f"{result.mape:,.1f}%", "Zero-safe percentage error", "good"),
            (
                "Vs. seasonal naive",
                f"{baseline_improvement:+.1f}%" if baseline_improvement is not None else "N/A",
                f"Baseline MAE {result.baseline_mae:,.1f}",
                "good" if baseline_improvement and baseline_improvement > 0 else "watch",
            ),
        ]
    )

    figure = go.Figure()
    recent_history = result.history.tail(52)
    figure.add_trace(
        go.Scatter(
            x=recent_history.week_start,
            y=recent_history.actual_demand,
            name="Actual demand",
            line={"color": COLORS["ink"], "width": 2},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=result.validation.week_start,
            y=result.validation.predicted_demand,
            name="Holdout prediction",
            line={"color": COLORS["amber"], "dash": "dot", "width": 3},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=result.future.week_start,
            y=result.future.upper_80,
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=result.future.week_start,
            y=result.future.lower_80,
            name="Empirical 80% band",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(161, 61, 99, 0.15)",
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=result.future.week_start,
            y=result.future.forecast_demand,
            name="12-week forecast",
            line={"color": COLORS["berry"], "dash": "dash", "width": 3},
        )
    )
    figure.update_layout(
        title="Actual vs. holdout prediction and future forecast",
        xaxis_title=None,
        yaxis_title="Demand units",
        hovermode="x unified",
        legend_title=None,
    )
    curve_tab, plan_tab, method_tab = st.tabs(
        ["↗ Forecast curve", "▤ 12-week planning table", "◎ Model methodology"]
    )
    with curve_tab:
        section_header(
            "Validated demand outlook",
            "Observed demand, holdout predictions, point forecast, and empirical uncertainty.",
        )
        st.plotly_chart(style_figure(figure), width="stretch")
        st.caption(
            f"The latest observed demand is {last_actual:,.0f} units. Accuracy is evaluated on the "
            "final 12 observed weeks, which are excluded from validation training."
        )

    with plan_tab:
        section_header(
            "Forward planning horizon",
            "Point demand and empirical lower/upper bounds for each of the next 12 weeks.",
        )
        st.dataframe(
            result.future,
            width="stretch",
            hide_index=True,
            column_config={
                "week_start": st.column_config.DateColumn("Week Starting", format="MMM D, YYYY"),
                "forecast_demand": st.column_config.NumberColumn(
                    "Point Forecast", format="%.1f"
                ),
                "lower_80": st.column_config.NumberColumn("Lower 80%", format="%.1f"),
                "upper_80": st.column_config.NumberColumn("Upper 80%", format="%.1f"),
            },
        )

    with method_tab:
        section_header(
            "Transparent forecasting method",
            "A compact model card for discussing validation choices and limitations.",
        )
        command_strip(
            [
                ("Training history", "92 weeks", "Latest 12 weeks held out", "info"),
                ("Seasonality", "52 / 26 / 13", "Fourier annual, semiannual, quarterly", "info"),
                ("Benchmark", "Seasonal naive", "Same week one year earlier", "watch"),
                ("Uncertainty", "Empirical 80%", "Holdout residual quantiles", "good"),
            ]
        )
        st.markdown(
            '<div class="status-note"><b>Interpretation:</b> the interval is an empirical planning '
            "band, not a calibrated clinical or financial confidence interval. Product-location "
            "accuracy should be reviewed before operational commitment.</div>",
            unsafe_allow_html=True,
        )


def show_replenishment() -> None:
    page_header(
        "Replenishment Recommendations",
        "Order-up-to recommendations that combine lead-time demand, a four-week review period, and safety stock.",
    )
    all_inventory = get_inventory_health()
    warehouse_options = {"All distribution centers": None} | dict(
        zip(
            all_inventory["warehouse_name"].drop_duplicates(),
            all_inventory["warehouse_id"].drop_duplicates(),
        )
    )
    with st.container(border=True):
        section_header(
            "Planning controls",
            "Choose a distribution center to create a focused net purchase recommendation.",
            "ORDER SCOPE",
        )
        warehouse_label = st.selectbox("Distribution center", list(warehouse_options))
    recommendations = get_replenishment_recommendations(
        warehouse_id=warehouse_options[warehouse_label]
    )
    critical = recommendations.loc[recommendations.stockout_risk == "Critical"]
    command_strip(
        [
            ("Recommended orders", f"{len(recommendations):,}", warehouse_label, "info"),
            (
                "Recommended units",
                f"{int(recommendations.recommended_order_quantity.sum()):,}",
                "Net of usable stock and open POs",
                "watch",
            ),
            (
                "Purchase value",
                money(recommendations.estimated_order_value.sum()),
                "Estimated at standard unit cost",
                "info",
            ),
            (
                "Critical orders",
                f"{len(critical):,}",
                "Positions below safety stock",
                "risk" if len(critical) else "good",
            ),
        ]
    )

    by_warehouse = (
        recommendations.groupby("warehouse_name", as_index=False)
        .agg(
            recommended_units=("recommended_order_quantity", "sum"),
            estimated_order_value=("estimated_order_value", "sum"),
        )
        .sort_values("estimated_order_value")
    )
    allocation_tab, queue_tab, logic_tab = st.tabs(
        ["◉ Capital allocation", "⇄ Order queue", "ƒ Planning logic"]
    )
    with allocation_tab:
        section_header(
            "Recommended capital allocation",
            "Purchase value and unit volume by distribution center after incoming supply.",
        )
        fig = px.bar(
            by_warehouse,
            x="estimated_order_value",
            y="warehouse_name",
            orientation="h",
            color="recommended_units",
            color_continuous_scale=["#F5DEC0", COLORS["amber"], COLORS["plum"]],
            title="Recommended purchase value by distribution center",
        )
        fig.update_layout(xaxis_tickprefix="$", yaxis_title=None, coloraxis_colorbar_title="Units")
        st.plotly_chart(style_figure(fig), width="stretch")

    with queue_tab:
        section_header(
            "Net replenishment queue",
            "Order candidates prioritized by risk and lowest weeks of supply.",
        )
        st.dataframe(
            recommendations[
                [
                    "product_id",
                    "product_name",
                    "warehouse_name",
                    "stockout_risk",
                    "weeks_of_supply",
                    "inventory_quantity",
                    "on_order_quantity",
                    "inventory_position",
                    "reorder_point",
                    "safety_stock",
                    "recommended_order_quantity",
                    "estimated_order_value",
                ]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "estimated_order_value": st.column_config.NumberColumn(
                    "Estimated Order Value", format="$%.2f"
                ),
                "weeks_of_supply": st.column_config.NumberColumn(
                    "Weeks of Supply", format="%.1f"
                ),
            },
        )

    with logic_tab:
        section_header(
            "Replenishment policy",
            "The order-up-to calculation is transparent and independently testable.",
        )
        st.markdown(
            '<div class="status-note"><b>Order quantity</b> = max(0, demand × '
            '(lead-time weeks + 4-week review period) + safety stock − usable on-hand inventory '
            '− open purchase-order quantity). Expired batches are excluded from usable stock.</div>',
            unsafe_allow_html=True,
        )
        command_strip(
            [
                ("Demand basis", "Trailing 12 weeks", "Average weekly demand", "info"),
                ("Review period", "4 weeks", "Planning cycle coverage", "info"),
                ("Incoming supply", "Open POs", "Subtracted before new order", "good"),
                ("Expired stock", "Excluded", "Not available for fulfillment", "risk"),
            ]
        )


ensure_database()

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-logo">Rx</div>
            <div><strong>Pharma Operations</strong><span>Intelligence Platform</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="date-badge">● Simulation date&nbsp; {SIMULATION_DATE}</div>',
        unsafe_allow_html=True,
    )
    page = st.radio(
        "Workspace",
        [
            "Executive Overview",
            "Inventory Risk",
            "Expiry Risk",
            "Supplier Performance",
            "Demand Forecast",
            "Replenishment Recommendations",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    if st.button("↻ Rebuild demo data", key="sidebar-rebuild"):
        try:
            with st.spinner("Rebuilding analytics database…"):
                run_pipeline()
                st.cache_data.clear()
            st.success("Data rebuilt successfully.")
            st.rerun()
        except DASHBOARD_ERRORS as exc:
            LOGGER.exception("Sidebar database rebuild failed")
            st.error(f"Rebuild failed: {type(exc).__name__}: {exc}")
    st.caption("Synthetic portfolio data · No patient information")

PAGES = {
    "Executive Overview": show_executive_overview,
    "Inventory Risk": show_inventory_risk,
    "Expiry Risk": show_expiry_risk,
    "Supplier Performance": show_supplier_performance,
    "Demand Forecast": show_demand_forecast,
    "Replenishment Recommendations": show_replenishment,
}

try:
    PAGES[page]()
    page_footer()
except DASHBOARD_ERRORS as exc:
    LOGGER.exception("Dashboard page failed: %s", page)
    show_recovery_error(
        f"Unable to load {page}",
        "The page encountered a data or calculation problem. Rebuild the analytics database and try again.",
        exc,
        page.lower().replace(" ", "-"),
    )
