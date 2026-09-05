"""Dash application factory — no external stylesheets, no dash-bootstrap-components."""

import os
import secrets

import dash

app = dash.Dash(
    __name__,
    assets_folder="../assets",
    suppress_callback_exceptions=True,
    title="Spin Rate — Penetration × Velocity",
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": "Every item plotted by distribution penetration against velocity, bubble-sized by dollars, across four quadrants."},
        {"property": "og:title", "content": "Spin Rate: Penetration and Velocity"},
        {"property": "og:description", "content": "Every item plotted by distribution penetration against velocity, bubble-sized by dollars, across four quadrants."},
        {"property": "og:type", "content": "website"},
        {"property": "og:url", "content": "https://spinrate.lailarallc.com/"},
        {"property": "og:image", "content": "https://lailarallc.com/og/s/spinrate.png"},
        {"property": "og:image:secure_url", "content": "https://lailarallc.com/og/s/spinrate.png"},
        {"property": "og:image:type", "content": "image/png"},
        {"property": "og:image:width", "content": "1200"},
        {"property": "og:image:height", "content": "630"},
        {"property": "og:image:alt", "content": "Spin Rate: Penetration and Velocity"},
        {"name": "twitter:card", "content": "summary_large_image"},
        {"name": "twitter:image", "content": "https://lailarallc.com/og/s/spinrate.png"},
    ],
)
server = app.server
server.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# ── Branded loading overlay ──────────────────────────────────────────
# Spin Rate is sent to prospects as a cold link, so the first hydration
# (Dash renderer boot + the quadrant data callback) leaves a blank white
# screen for several seconds. That reads as broken.
#
# This overlay is plain static HTML/CSS injected directly into the page
# body, so the browser paints it on the *first frame* — before any Dash
# JavaScript runs. It does NOT depend on the Dash renderer being ready
# (that would defeat the purpose). A small inline script watches the DOM
# for the rendered quadrant Plotly chart and fades the overlay out the
# moment that chart exists, i.e. when the default tab is interactive.
#
# Colors/fonts are literal Lailara tokens (not CSS variables) so the
# overlay is styled even before the external stylesheet finishes loading.
_LOADING_OVERLAY = """
    <style>
      #spinrate-loading {
        position: fixed;
        inset: 0;
        z-index: 99999;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #f5f3ee; /* Canvas — London-100 warmed */
        transition: opacity 300ms ease-out;
      }
      #spinrate-loading.sr-hide { opacity: 0; pointer-events: none; }
      .sr-load-inner { text-align: center; padding: 0 24px; }
      .sr-load-spinner {
        width: 46px;
        height: 46px;
        margin: 0 auto 26px;
        border: 3px solid #d9d9d9;     /* London-85 gridline */
        border-top-color: #1f2e7a;     /* Chicago-20 navy */
        border-radius: 50%;
        animation: sr-spin 900ms linear infinite;
      }
      .sr-load-brand {
        font-family: 'Playfair Display', Georgia, 'Times New Roman', serif;
        font-size: 26px;              /* DS Brand-name step; 20px mobile below */
        font-weight: 700;
        color: #0d0d0d;                /* Ink */
        letter-spacing: -0.01em;
        line-height: 1.2;
      }
      .sr-load-sub {
        font-family: 'Source Sans 3', 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 12px;
        font-weight: 600;
        color: #595959;                /* Text secondary */
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-top: 10px;
      }
      .sr-load-hint {
        font-family: 'Source Sans 3', 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 14px;
        font-weight: 400;
        color: #595959;                /* Text secondary */
        margin-top: 22px;
      }
      @keyframes sr-spin { to { transform: rotate(360deg); } }
      @media (prefers-reduced-motion: reduce) {
        #spinrate-loading { transition: none; }
        .sr-load-spinner {
          animation: none;
          border-color: #1f2e7a;       /* full navy ring, no motion */
        }
      }
      @media (max-width: 640px) {
        .sr-load-brand { font-size: 20px; }
      }
    </style>
    <div id="spinrate-loading" role="status" aria-live="polite" aria-label="Loading Spin Rate">
      <div class="sr-load-inner">
        <div class="sr-load-spinner" aria-hidden="true"></div>
        <div class="sr-load-brand">Spin&nbsp;Rate</div>
        <div class="sr-load-sub">Penetration &times; Velocity</div>
        <div class="sr-load-hint">Preparing the quadrant&hellip;</div>
      </div>
    </div>
    <script>
      (function () {
        var SAFETY_MS = 20000;
        function hide() {
          var el = document.getElementById('spinrate-loading');
          if (!el || el.classList.contains('sr-hide')) return;
          el.classList.add('sr-hide');
          setTimeout(function () {
            if (el && el.parentNode) el.parentNode.removeChild(el);
          }, 400);
        }
        // The default Quadrant tab is interactive once Plotly has drawn its
        // chart inside #quadrant-chart (the data callback has returned).
        function ready() {
          return !!document.querySelector('#quadrant-chart .js-plotly-plot');
        }
        function check() {
          if (ready()) { hide(); return true; }
          return false;
        }
        if (check()) return;
        var obs = new MutationObserver(function () {
          if (check()) obs.disconnect();
        });
        obs.observe(document.documentElement, { childList: true, subtree: true });
        // Never trap the visitor behind the overlay if the chart never paints.
        setTimeout(function () { obs.disconnect(); hide(); }, SAFETY_MS);
      })();
    </script>
"""

app.index_string = """<!DOCTYPE html>
<html lang="en">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        __LOADING_OVERLAY__
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>""".replace("__LOADING_OVERLAY__", _LOADING_OVERLAY)
