"""Client-mode CLI for Spin Rate.

Computes SPPD (sales per point of distribution) and dollarized expansion upside
on a client's own POS data via the shared ``lailara_engagement`` POS-intake
layer, plus a Spin-Rate-specific products file (wholesale price).

The P1 this tool exists to not repeat: **upside is valued at wholesale while
current revenue is retail scan.** Both bases are declared and printed
structurally — Current $ carries the ``scan_basis`` word (retail scan), the
upside columns are explicitly labeled wholesale — so a wholesale projection can
never be read as scan dollars.

Required inputs: weekly **scans** (units + retail-scan dollars), the
**authorization** log (active distribution), the **store** dimension, and a
**products** file (sku, product_line, wholesale_price). A missing required
column blocks with a branded Data Readiness Report; a clean run writes a
draft-watermarked, provenance-footed **SPPD & Expansion Upside** deliverable
(HTML) + the ranked upside table (CSV) to ``client-output/`` only.

Usage:
    python client_mode.py --config engagement.yml [--out client-output] [--final]
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import pandas as pd

from app.calculations import calculate_expansion_upside, calculate_sppd
from lailara_engagement import (
    ColumnSpec,
    PreflightSpec,
    build_provenance,
    load_config,
    pos,
    read_table,
    run_preflight,
    validation_status_label,
    write_report,
)
from lailara_engagement import palette as P
from lailara_engagement.provenance import Provenance

TOOL = "spinrate"
TOOL_VERSION = "1.0"


def _products_spec() -> PreflightSpec:
    return PreflightSpec(tool=TOOL, version=TOOL_VERSION, columns=[
        ColumnSpec(name="sku", dtype="identifier", required=True, spec_ref="INPUT-SPEC §Products"),
        ColumnSpec(name="product_line", dtype="string", required=True, spec_ref="INPUT-SPEC §Products"),
        ColumnSpec(name="wholesale_price", dtype="number", required=True, not_negative=True,
                   spec_ref="INPUT-SPEC §Products"),
    ])


def _resolve_inputs(config, args):
    ci = config.raw.get("inputs") or {}
    return {
        "scans": args.scans or ci.get("scans"),
        "authorizations": args.auth or ci.get("authorizations") or ci.get("auth"),
        "stores": args.stores or ci.get("stores"),
        "products": args.products or ci.get("products"),
    }


def _fmt_dollars(v):
    return "—" if v is None else f"${v:,.0f}"


def _deliverable_html(config, table, totals, window_label, basis_word,
                      limitations, provenance: Provenance, *, draft: bool) -> str:
    esc = html.escape
    draft_class = " ll-draft" if draft else ""
    rows = "".join(
        f"<tr><td>{esc(str(r['product_name']))}</td><td>{esc(str(r['sku']))}</td>"
        f"<td class=num>{int(r['current_doors'])}</td>"
        f"<td class=num>{_fmt_dollars(r['current_dollars'])}</td>"
        f"<td class=num>{_fmt_dollars(r['upside_median_dollars'])}</td>"
        f"<td class=num>{_fmt_dollars(r['upside_leader_dollars'])}</td></tr>"
        for _, r in table.iterrows()
    )
    lim_html = "".join(f"<li>{esc(x)}</li>" for x in limitations)
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>SPPD &amp; Expansion Upside — {esc(config.client_name)}</title>
<style>{_css(draft)}</style></head>
<body class="{draft_class.strip()}"><main class=ll-page>
<header class=ll-header>
  <div class=ll-eyebrow>Lailara LLC · Spin Rate</div>
  <h1 class=ll-title>SPPD &amp; Expansion Upside</h1>
  <div class=ll-client>
    <div><span class=ll-k>Client</span> {esc(config.client_name)}</div>
    <div><span class=ll-k>Engagement</span> {esc(config.engagement_id)}</div>
    <div><span class=ll-k>As of</span> {esc(config.as_of_date.isoformat())}</div>
    <div><span class=ll-k>Prepared by</span> {esc(config.prepared_by)}</div>
  </div>
</header>
<section class=ll-banner>
  <div class=ll-score>{_fmt_dollars(totals['median'])} expansion upside at peer-median doors</div>
  <div>{_fmt_dollars(totals['leader'])} at category-leader doors ·
       {_fmt_dollars(totals['current'])} current {esc(basis_word)} revenue</div>
  <div class=ll-basis>Basis: <strong>upside is valued at WHOLESALE price</strong>;
       current revenue is {esc(basis_word)} dollars — the two are different bases,
       shown side by side and never mixed.<br>Window: {esc(window_label)}</div>
</section>
<section class=ll-section>
  <h2 class=ll-h2>Upside by item — current ({esc(basis_word)}) vs projected (wholesale)</h2>
  <table class=ll-table><thead><tr><th>Item</th><th>SKU</th><th>Doors</th>
  <th>Current $ ({esc(basis_word)})</th><th>Upside @ median (wholesale)</th>
  <th>Upside @ leader (wholesale)</th></tr></thead><tbody>{rows}</tbody></table>
  <p class=ll-note>Full ranked table exported to the accompanying CSV.</p>
</section>
<section class=ll-section>
  <h2 class=ll-h2>Data limitations</h2>
  <ul class=ll-limitations>{lim_html}</ul>
</section>
{provenance.to_html()}
</main></body></html>"""


def _css(draft: bool) -> str:
    draft_css = (
        ".ll-draft::before{content:'DRAFT';position:fixed;top:50%;left:50%;"
        "transform:translate(-50%,-50%) rotate(-32deg);font-family:var(--s);"
        "font-size:22vw;font-weight:700;color:rgba(204,16,10,.06);z-index:0;"
        "pointer-events:none;white-space:nowrap}" if draft else ""
    )
    return f"""
:root{{--s:{P.LL_SERIF};--f:{P.LL_SANS}}}
*{{box-sizing:border-box}}
body{{margin:0;background:{P.LL_CANVAS};color:{P.LL_TEXT};font-family:var(--f);line-height:1.6}}
.ll-page{{position:relative;z-index:1;max-width:{P.LL_MAX_WIDTH};margin:0 auto;padding:48px 24px}}
.ll-header{{border-bottom:1px solid {P.LL_GRIDLINE};padding-bottom:24px;margin-bottom:24px}}
.ll-eyebrow{{font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:{P.LL_RED};font-weight:600}}
.ll-title{{font-family:var(--s);font-weight:700;color:{P.LL_INK};font-size:34px;margin:8px 0 16px}}
.ll-client{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px 24px;font-size:14px}}
.ll-k{{display:block;color:{P.LL_TEXT_SEC};font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
.ll-banner{{border-radius:2px;padding:16px 20px;margin-bottom:32px;background:{P.LL_HK_SURFACE};color:{P.LL_HK_DARK}}}
.ll-score{{font-family:var(--s);font-weight:700;font-size:22px}}
.ll-basis{{font-size:12px;color:{P.LL_TEXT_SEC};margin-top:8px}}
.ll-section{{margin:0 0 32px}}
.ll-h2{{font-family:var(--s);font-weight:700;color:{P.LL_INK};font-size:22px;
margin:0 0 12px;padding-bottom:6px;border-bottom:1px solid {P.LL_GRIDLINE}}}
.ll-note{{font-size:13px;color:{P.LL_TEXT_SEC};margin-top:8px}}
.ll-table{{width:100%;border-collapse:collapse;font-size:14px}}
.ll-table th{{text-align:left;background:{P.LL_CHICAGO};color:#fff;padding:8px 12px}}
.ll-table td{{padding:8px 12px;border-bottom:1px solid {P.LL_GRIDLINE}}}
.ll-limitations{{margin:0;padding-left:20px}}.ll-limitations li{{margin-bottom:6px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.ll-provenance{{margin-top:40px;background:{P.LL_CARD_BG};color:{P.LL_CARD_TEXT};
padding:20px 24px;border-radius:2px;font-size:13px}}
.ll-prov-title{{font-family:var(--s);font-weight:700;font-size:16px;margin-bottom:8px}}
.ll-provenance div{{margin-bottom:4px;color:{P.LL_CARD_SUBTITLE}}}
.ll-provenance strong{{color:{P.LL_CARD_TEXT}}}
.ll-prov-inputs{{width:100%;border-collapse:collapse;margin-top:8px}}
.ll-prov-inputs th{{text-align:left;border-bottom:1px solid rgba(255,255,255,.12);padding:4px 8px;color:{P.LL_CARD_MUTED}}}
.ll-prov-inputs td{{padding:4px 8px;border-bottom:1px solid rgba(255,255,255,.08);color:{P.LL_CARD_SUBTITLE}}}
.ll-prov-brand{{margin-top:12px;font-family:var(--s);color:{P.LL_CARD_MUTED}}}
{draft_css}
@media print{{body{{background:#fff}}}}
"""


def run(config_path: str, out_dir: str, args, *, final: bool = False) -> dict:
    config = load_config(config_path)
    inputs = _resolve_inputs(config, args)
    week_conv_name, _wd = pos.resolve_week_convention(config)
    scan_basis = pos.resolve_scan_basis(config)          # current revenue basis (retail scan)
    basis_word = pos.scan_basis_label(scan_basis)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    required = {
        "scans": pos.scan_spec(tool=TOOL, version=TOOL_VERSION, week_convention=week_conv_name),
        "authorizations": pos.authorization_spec(tool=TOOL, version=TOOL_VERSION),
        "stores": pos.store_spec(tool=TOOL, version=TOOL_VERSION),
        "products": _products_spec(),
    }
    missing = [k for k, v in inputs.items() if k in required and not v]
    if missing:
        raise SystemExit(f"missing required input(s): {', '.join(missing)}.")

    reads, reports, frames = {}, {}, {}
    for key, spec in required.items():
        read = read_table(inputs[key])
        report, frame = pos.intake(read, spec, config) if key != "products" else \
            (run_preflight(read, spec, config), None)
        reads[key], reports[key] = read, report
        frames[key] = frame if frame is not None else (
            pos.to_frame(read, report, spec) if report.passed else None)

    reports["scans"].disclosures.extend(pos.declared_disclosures(week_conv_name, scan_basis))

    blocked = {k: r for k, r in reports.items() if not r.passed}
    provenance = build_provenance(
        tool=TOOL, tool_version=TOOL_VERSION, inputs=[reads[k] for k in required], config=config,
        validation_status=validation_status_label("failed" if blocked else "clean",
                                                   sum(r.n_warnings for r in reports.values())),
        extra={"Week convention": week_conv_name,
               "Current revenue basis": f"{basis_word} dollars",
               "Upside basis": "wholesale dollars"},
    )
    if blocked:
        written = {}
        for key, report in blocked.items():
            paths = write_report(report, config, str(out), provenance=provenance, draft=not final,
                                 basename=f"data-readiness-{key}",
                                 title=f"Spin Rate Data Readiness Report — {key}")
            written[key] = paths["html"]
        return {"status": "blocked", "blocked_files": list(blocked), "readiness_reports": written}

    scans, auth, stores, products = (frames["scans"], frames["authorizations"],
                                     frames["stores"], frames["products"])
    as_of = pd.Timestamp(config.as_of_date)
    win = scans[scans["week_ending"] <= as_of]
    if win.empty:
        raise SystemExit(f"as_of_date {config.as_of_date} precedes every scan week.")
    n_weeks = win["week_ending"].nunique()
    days = n_weeks * 7.0

    sppd = calculate_sppd(win[win["units_sold"] > 0], days)
    dist = auth[["sku", "store_id"]].drop_duplicates()
    bench = products[["product_line"]].drop_duplicates()
    upside = calculate_expansion_upside(sppd, dist, stores, products, bench, days_in_period=days)

    # Current retail-scan dollars per SKU (the OTHER basis, kept separate).
    cur = win.groupby("sku", as_index=False)["dollars_sold"].sum().rename(
        columns={"dollars_sold": "current_dollars"})
    table = upside.merge(cur, on="sku", how="left").merge(
        products[["sku", "product_line"]], on="sku", how="left", suffixes=("", "_p"))
    table["current_dollars"] = table["current_dollars"].fillna(0.0)
    table["product_name"] = table["sku"]
    table = table.sort_values("upside_median_dollars", ascending=False).reset_index(drop=True)

    totals = {
        "median": round(float(table["upside_median_dollars"].sum()), 2),
        "leader": round(float(table["upside_leader_dollars"].sum()), 2),
        "current": round(float(table["current_dollars"].sum()), 2),
    }
    first, last = win["week_ending"].min(), win["week_ending"].max()
    window_label = (f"scan weeks {first.strftime('%b %d, %Y')} – {last.strftime('%b %d, %Y')} "
                    f"({n_weeks} weeks) · as of {as_of.strftime('%b %d, %Y')}")

    limitations = []
    for key, report in reports.items():
        for f in report.findings:
            if f.severity == "warning":
                limitations.append(f"[{key}] {f.message}")
    if not limitations:
        limitations.append("No warnings — all inputs passed preflight cleanly.")

    csv_path = out / "expansion-upside.csv"
    table.to_csv(csv_path, index=False)
    html_path = out / "sppd-expansion-upside.html"
    html_path.write_text(_deliverable_html(config, table, totals, window_label, basis_word,
                                            limitations, provenance, draft=not final), encoding="utf-8")
    return {"status": "ok", "total_median_upside": totals["median"],
            "total_leader_upside": totals["leader"], "current_revenue": totals["current"],
            "report": str(html_path), "exceptions_csv": str(csv_path),
            "n_warnings": sum(r.n_warnings for r in reports.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="spinrate client mode")
    ap.add_argument("--config", required=True)
    ap.add_argument("--scans"); ap.add_argument("--auth"); ap.add_argument("--stores")
    ap.add_argument("--products"); ap.add_argument("--out", default="client-output")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args(argv)
    result = run(args.config, args.out, args, final=args.final)
    if result["status"] == "blocked":
        print("BLOCKED — data not ready. Readiness report(s):")
        for key, path in result["readiness_reports"].items():
            print(f"  {key}: {path}")
        return 3
    print(f"expansion upside {_fmt_dollars(result['total_median_upside'])} (median, wholesale) · "
          f"current {_fmt_dollars(result['current_revenue'])} (retail scan)"
          + (f" · {result['n_warnings']} warning(s)" if result["n_warnings"] else ""))
    print(f"report -> {result['report']}\ncsv    -> {result['exceptions_csv']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
