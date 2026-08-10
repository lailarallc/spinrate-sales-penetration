"""Demo golden + P1 regression lock — Spin Rate.

Spin Rate renders its demo from Postgres at runtime (no committed demo JSON), so
the lock is on the **engine** plus the two 07-31 P1 fixes that the audit flagged
and that the UI must never regress:

1. **Window mislabel.** The expansion hero once said "this quarter" / "quarterly
   upside" while the default window is four quarters. The label is now computed
   from the selected window (`f"{start_q}–{end_q}"`), and the banned literals are
   gone. Locked at the source level (the callback needs a DB to run).
2. **Basis words.** Upside is valued at **wholesale** while Current $ is **retail
   scan** — both must be labeled so a CFO can't read a wholesale projection as
   scan dollars. Locked on the column definitions.

Plus an engine golden on `calculate_expansion_upside` (upside = incremental
doors × SPPD × days × wholesale price).

If any assertion fails, STOP: a demo golden moved.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.calculations import calculate_expansion_upside, calculate_sppd

ROOT = Path(__file__).resolve().parent.parent
EXPANSION_SRC = (ROOT / "app" / "views" / "expansion.py").read_text(encoding="utf-8")


# ── P1 #1: window label computed from the selection, no stale literals ───────

def test_no_hardcoded_quarter_window_literals_in_ui():
    lowered = EXPANSION_SRC.lower()
    assert "this quarter" not in lowered
    assert "quarterly upside" not in lowered


def test_window_label_is_computed_from_selected_quarters():
    # the fix: label derives from start/end quarter, not a hardcoded window word.
    assert 'f"{start_q}–{end_q}"' in EXPANSION_SRC
    assert "in upside over {window_label}" in EXPANSION_SRC


# ── P1 #2: basis words on the columns (retail scan vs wholesale) ─────────────

def test_current_dollars_labeled_retail_scan():
    assert "Current $ (retail scan)" in EXPANSION_SRC


def test_upside_columns_labeled_wholesale():
    assert "Upside @ Median (wholesale)" in EXPANSION_SRC
    assert "Upside @ 75th (wholesale)" in EXPANSION_SRC
    assert "Upside @ Leader (wholesale)" in EXPANSION_SRC
    # tooltip ties the wholesale upside to the same period as Current $.
    assert "valued at wholesale price (same period as Current $)" in EXPANSION_SRC


# ── engine golden ────────────────────────────────────────────────────────────

def _fixture():
    doors = {"A": 3, "B": 6, "C": 9}
    scans = [(sku, f"S{s}", 91 * 2) for sku, n in doors.items() for s in range(n)]
    scan_df = pd.DataFrame(scans, columns=["sku", "store_id", "units_sold"])
    dist = scan_df[["sku", "store_id"]].drop_duplicates()
    stores = pd.DataFrame([(f"S{s}", "B") for s in range(10)], columns=["store_id", "volume_tier"])
    products = pd.DataFrame([("A", "AS", 10.0), ("B", "AS", 10.0), ("C", "AS", 10.0)],
                            columns=["sku", "product_line", "wholesale_price"])
    bench = pd.DataFrame([("AS",)], columns=["product_line"])
    return scan_df, dist, stores, products, bench


def test_expansion_upside_engine_is_pinned():
    scan_df, dist, stores, products, bench = _fixture()
    sppd = calculate_sppd(scan_df, 91.0)
    assert set(sppd["sppd"]) == {2.0}          # 182 units / doors / 91 days = 2.0 per door-day
    up = calculate_expansion_upside(sppd, dist, stores, products, bench, days_in_period=91.0)
    a = up[up["sku"] == "A"].iloc[0]
    # (6-3) doors × 2.0 sppd × 91 days × $10 wholesale = $5,460 at median.
    assert round(a["upside_median_dollars"], 2) == 5460.00
    assert round(a["upside_leader_dollars"], 2) == 10920.00   # (9-3) × 2 × 91 × 10
    assert round(up["upside_median_dollars"].sum(), 2) == 5460.00
    assert round(up["upside_leader_dollars"].sum(), 2) == 16380.00
