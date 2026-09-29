#!/usr/bin/env python3
"""Exploration charts for the findings in docs/insights.md.

These are reading aids, not a dashboard. Each one exists to make a single
claim visible. Run after the star schema is built:

    python -m src.plot_insights

Writes output/fig_*.png. Read-only against the lake.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

STAR = Path("lake/processed/star")
RAW_REVIEWS = Path("lake/raw/olist/olist_order_reviews_dataset.csv")
OUT = Path("output")

INK = "#2C2E57"
MUTED = "#8F93B0"
FLAG = "#F87474"
OK = "#4076ED"
GRID = "#E6E8F0"

plt.rcParams.update({
    "figure.dpi": 140,
    "savefig.dpi": 140,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
})


def tbl(name: str) -> str:
    return f"read_parquet('{STAR / (name + '.parquet')}')"


def frame(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def finish(fig, ax, note: str, path: Path):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.text(0.01, 0.005, note, fontsize=8, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path}")


def fig_coverage(con):
    """Monthly volume, with the unusable months marked."""
    _, rs = frame(con, f"""
        SELECT strftime(order_purchase_timestamp, '%Y-%m') AS ym, count(*) AS n
        FROM {tbl('fact_orders')} GROUP BY 1 ORDER BY 1
    """)
    labels = [r[0] for r in rs]
    vals = [r[1] for r in rs]
    colors = [FLAG if v < 1000 else OK for v in vals]

    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar(range(len(vals)), vals, color=colors, width=0.7)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=90, fontsize=7)
    ax.set_ylabel("orders")
    ax.set_title("Monthly orders: the ends of the window are not real months")
    for i, (lab, v) in enumerate(zip(labels, vals)):
        if v < 1000:
            ax.text(i, v + 120, str(v), ha="center", fontsize=7, color=FLAG)
    ax.annotate("2016-11 has no rows at all",
                xy=(1.6, 3000), xytext=(3.2, 5200), fontsize=8, color=FLAG,
                arrowprops=dict(arrowstyle="->", color=FLAG, lw=1))
    ax.annotate("extract stops mid-collection",
                xy=(len(vals) - 1.4, 1500), xytext=(len(vals) - 8, 5200), fontsize=8, color=FLAG,
                arrowprops=dict(arrowstyle="->", color=FLAG, lw=1))
    finish(fig, ax, "Red bars are below 1,000 orders. Trend claims use 2017-02 to 2018-08 only.",
           OUT / "fig_coverage.png")


def fig_customer_key(con):
    """What the customer key choice does to repeat rate."""
    o, c = tbl("fact_orders"), tbl("dim_customers")
    (people, multi, mx) = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE n_customer_ids > 1), max(n_customer_ids) FROM {c}
    """).fetchone()
    repeat_person = con.execute(f"""
        WITH x AS (SELECT customer_sk, count(*) n FROM {o} WHERE order_status='delivered' GROUP BY 1)
        SELECT 100.0 * count(*) FILTER (WHERE n > 1) / count(*) FROM x
    """).fetchone()[0]
    # keyed on the per-order id, every order is a different customer by construction
    repeat_order = 0.0

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10, 4), gridspec_kw={"width_ratios": [1, 1.25]})
    ax.bar(["keyed on\nper-order id", "keyed on\nthe person"], [repeat_order, repeat_person],
           color=[FLAG, OK], width=0.55)
    ax.set_ylabel("repeat rate (%)")
    ax.set_ylim(0, max(4.0, repeat_person * 1.4))
    ax.set_title("Same data, two customer keys")
    for i, v in enumerate([repeat_order, repeat_person]):
        ax.text(i, v + 0.12, f"{v:.1f}%", ha="center", fontweight="bold")

    _, rs = frame(con, f"""
        SELECT n_customer_ids AS ids, count(*) AS people FROM {c}
        WHERE n_customer_ids > 1 GROUP BY 1 ORDER BY 1
    """)
    ax2.bar([str(r[0]) for r in rs], [r[1] for r in rs], color=OK, width=0.65)
    ax2.set_yscale("log")
    ax2.set_xlabel("per-order ids held by one person")
    ax2.set_ylabel("people (log)")
    ax2.set_title(f"{multi:,} people hold more than one; the largest holds {mx}")
    ax2.grid(axis="y", color=GRID, linewidth=0.8)
    ax2.set_axisbelow(True)

    fig.text(0.01, 0.005, f"{people:,} people in dim_customers.", fontsize=8, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "fig_customer_key.png")
    plt.close(fig)
    print(f"  wrote {OUT / 'fig_customer_key.png'}")


def _lateness(con):
    o = tbl("fact_orders")
    return frame(con, f"""
        WITH d AS (
            SELECT date_diff('day', order_estimated_delivery_date, order_delivered_customer_date) AS late,
                   review_score_avg AS r
            FROM {o} WHERE order_status='delivered' AND order_delivered_customer_date IS NOT NULL
        )
        SELECT CASE WHEN late <= 0 THEN 'on time\nor early'
                    WHEN late <= 7 THEN '1-7 days\nlate'
                    WHEN late <= 30 THEN '8-30 days\nlate'
                    ELSE 'over 30\ndays late' END AS bucket,
               count(*) AS n, round(avg(r), 2) AS avg_review,
               round(100.0 * count(*) FILTER (WHERE r <= 2) / count(*) FILTER (WHERE r IS NOT NULL), 1) AS pct_low
        FROM d GROUP BY 1
        ORDER BY CASE bucket WHEN 'on time\nor early' THEN 1 WHEN '1-7 days\nlate' THEN 2
                             WHEN '8-30 days\nlate' THEN 3 ELSE 4 END
    """)


def fig_lateness(con):
    """The headline relationship, and the bar that does not fit."""
    _, rs = _lateness(con)
    labels = [r[0] for r in rs]
    scores = [r[2] for r in rs]
    ns = [r[1] for r in rs]
    colors = [OK, OK, OK, FLAG]

    fig, ax = plt.subplots(figsize=(8, 4.4))
    bars = ax.bar(labels, scores, color=colors, width=0.6)
    ax.set_ylabel("average review score")
    ax.set_ylim(0, 5)
    ax.axhline(4.29, color=MUTED, linestyle=":", linewidth=1)
    ax.set_title("Missing the promised date costs more than a point and a half")
    for b, s, n in zip(bars, scores, ns):
        ax.text(b.get_x() + b.get_width() / 2, s + 0.09, f"{s}", ha="center", fontweight="bold")
        ax.text(b.get_x() + b.get_width() / 2, 0.12, f"n={n:,}", ha="center", fontsize=8, color="white")
    ax.annotate("this one goes the wrong way",
                xy=(3, scores[3] + 0.2), xytext=(1.75, 3.6), fontsize=9, color=FLAG,
                arrowprops=dict(arrowstyle="->", color=FLAG, lw=1.2))
    finish(fig, ax, "Lateness is measured against the date the customer was shown.",
           OUT / "fig_lateness_reviews.png")


def fig_review_timing(con):
    """Why the last bar goes the wrong way: the survey fires before delivery."""
    if not RAW_REVIEWS.exists():
        print(f"  skipped fig_review_timing ({RAW_REVIEWS} not found)")
        return
    o = tbl("fact_orders")
    _, rs = frame(con, f"""
        WITH r AS (SELECT order_id, review_creation_date FROM read_csv_auto('{RAW_REVIEWS}')),
        d AS (
            SELECT date_diff('day', o.order_estimated_delivery_date, o.order_delivered_customer_date) AS late,
                   date_diff('day', o.order_purchase_timestamp, r.review_creation_date) AS waited_at_review,
                   date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date) AS waited_total
            FROM {o} o JOIN r ON o.order_id = r.order_id
            WHERE o.order_status='delivered' AND o.order_delivered_customer_date IS NOT NULL
        )
        SELECT CASE WHEN late <= 0 THEN 'on time\nor early'
                    WHEN late <= 7 THEN '1-7 days\nlate'
                    WHEN late <= 30 THEN '8-30 days\nlate'
                    ELSE 'over 30\ndays late' END AS bucket,
               round(avg(waited_at_review), 1) AS at_review, round(avg(waited_total), 1) AS total
        FROM d GROUP BY 1
        ORDER BY CASE bucket WHEN 'on time\nor early' THEN 1 WHEN '1-7 days\nlate' THEN 2
                             WHEN '8-30 days\nlate' THEN 3 ELSE 4 END
    """)
    labels = [r[0] for r in rs]
    at_review = [r[1] for r in rs]
    total = [r[2] for r in rs]
    x = range(len(labels))

    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.bar([i - 0.19 for i in x], at_review, width=0.36, color=OK, label="days waited when the survey arrived")
    ax.bar([i + 0.19 for i in x], total, width=0.36, color=FLAG, label="days waited in total")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("days since purchase")
    ax.set_title("The customer rates the wait at the survey, not the wait in the end")
    for i, (a, b) in enumerate(zip(at_review, total)):
        ax.text(i - 0.19, a + 1.2, f"{a:g}", ha="center", fontsize=8, fontweight="bold")
        ax.text(i + 0.19, b + 1.2, f"{b:g}", ha="center", fontsize=8, color=FLAG, fontweight="bold")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    finish(fig, ax,
           "Every order more than 7 days late was rated before it arrived. The gap between the two bars is invisible to the reviewer.",
           OUT / "fig_review_timing.png")


def fig_states(con):
    """Distance costs twice: slower delivery and a larger freight share."""
    o, c = tbl("fact_orders"), tbl("dim_customers")
    _, rs = frame(con, f"""
        SELECT c.state, count(*) AS orders,
               round(avg(date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 1) AS days,
               round(100.0 * count(*) FILTER (WHERE o.delivered_on_time = false) / count(*), 1) AS late_pct,
               round(avg(o.review_score_avg), 2) AS review
        FROM {o} o JOIN {c} c ON o.customer_sk = c.customer_sk
        WHERE o.order_status='delivered' AND o.order_delivered_customer_date IS NOT NULL
        GROUP BY 1 HAVING count(*) >= 500
    """)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for state, orders, days, late, review in rs:
        size = 40 + (orders ** 0.62)
        highlight = state == "RJ"
        ax.scatter(days, late, s=size, color=FLAG if highlight else OK,
                   alpha=0.85 if highlight else 0.55, edgecolor="white", linewidth=1, zorder=3)
        ax.annotate(state, (days, late), textcoords="offset points", xytext=(0, -3),
                    ha="center", fontsize=8, fontweight="bold" if highlight else "normal",
                    color=INK if not highlight else FLAG)
    ax.set_xlabel("average days from purchase to delivery")
    ax.set_ylabel("% delivered later than promised")
    ax.set_title("RJ is late like a far state while delivering like a near one")
    ax.annotate("2nd largest market,\n12,344 orders",
                xy=(15.2, 13.5), xytext=(17.5, 17.5), fontsize=8, color=FLAG,
                arrowprops=dict(arrowstyle="->", color=FLAG, lw=1))
    finish(fig, ax, "Bubble size is order volume. States with at least 500 delivered orders.",
           OUT / "fig_states.png")


def fig_order_value(con):
    """Why the headline number should be a median."""
    o = tbl("fact_orders")
    _, rs = frame(con, f"""
        SELECT gmv_items FROM {o} WHERE order_status='delivered' AND gmv_items > 0 AND gmv_items <= 600
    """)
    vals = [r[0] for r in rs]
    mean, med = con.execute(f"""
        SELECT avg(gmv_items), median(gmv_items) FROM {o} WHERE order_status='delivered'
    """).fetchone()

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.hist(vals, bins=60, color=OK, alpha=0.85)
    ax.axvline(med, color=INK, linewidth=1.6, label=f"median {med:.0f}")
    ax.axvline(mean, color=FLAG, linewidth=1.6, label=f"mean {mean:.0f}")
    ax.set_xlabel("order value")
    ax.set_ylabel("orders")
    ax.set_title("Order value is right-skewed, so the mean sits above most orders")
    ax.legend(frameon=False, fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):,}"))
    finish(fig, ax, "Chart clipped at 600 for readability. The largest single order is 13,440.",
           OUT / "fig_order_value.png")


def main() -> int:
    global STAR, OUT
    ap = argparse.ArgumentParser(description="Exploration charts for docs/insights.md")
    ap.add_argument("--star-dir", type=Path, default=STAR)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    STAR, OUT = args.star_dir, args.out
    if not (STAR / "fact_orders.parquet").exists():
        print(f"No star schema at {STAR}. Run `python -m src.run_pipeline --skip-s3` first.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    print("Charts:")
    fig_coverage(con)
    fig_customer_key(con)
    fig_lateness(con)
    fig_review_timing(con)
    fig_states(con)
    fig_order_value(con)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
