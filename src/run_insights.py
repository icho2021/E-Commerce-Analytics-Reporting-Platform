#!/usr/bin/env python3
"""Stage 4 - Insight layer on the processed star schema.

Regenerates every number quoted in docs/insights.md. Read-only: it never
writes into lake/processed. Output goes to output/insights.json plus a
readable report on stdout.

    python -m src.run_insights
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

STAR = Path("lake/processed/star")
OUT = Path("output/insights.json")

DELIVERED = "o.order_status = 'delivered'"


def t(name: str) -> str:
    return f"read_parquet('{STAR / (name + '.parquet')}')"


def one(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def coverage(con) -> dict:
    """Where the data starts and stops, and where it is thin."""
    first, last = one(con, f"SELECT min(order_purchase_timestamp), max(order_purchase_timestamp) FROM {t('fact_orders')} o")
    monthly = rows(con, f"""
        SELECT strftime(order_purchase_timestamp, '%Y-%m') AS year_month, count(*) AS orders
        FROM {t('fact_orders')} o GROUP BY 1 ORDER BY 1
    """)
    full = [m for m in monthly if m["orders"] >= 1000]
    thin = [m for m in monthly if m["orders"] < 1000]
    present = {m["year_month"] for m in monthly}
    expected, cur = [], datetime(first.year, first.month, 1)
    while cur <= datetime(last.year, last.month, 1):
        expected.append(cur.strftime("%Y-%m"))
        cur = datetime(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return {
        "first_order": str(first),
        "last_order": str(last),
        "months_observed": len(monthly),
        "missing_months": [m for m in expected if m not in present],
        "thin_months": thin,
        "reliable_window": {"start": full[0]["year_month"], "end": full[-1]["year_month"]} if full else None,
        "monthly_orders": monthly,
    }


def integrity(con) -> dict:
    """Contradictions between status fields and timestamp fields."""
    o = t("fact_orders")
    delivered_no_date = one(con, f"SELECT count(*) FROM {o} o WHERE {DELIVERED} AND order_delivered_customer_date IS NULL")[0]
    not_delivered_has_date = rows(con, f"""
        SELECT order_status, count(*) AS n FROM {o} o
        WHERE order_status <> 'delivered' AND order_delivered_customer_date IS NOT NULL
        GROUP BY 1 ORDER BY n DESC
    """)
    no_review = one(con, f"SELECT count(*) FROM {o} o WHERE n_reviews = 0 OR n_reviews IS NULL")[0]
    total = one(con, f"SELECT count(*) FROM {o} o")[0]
    return {
        "orders_total": total,
        "delivered_without_delivery_date": delivered_no_date,
        "not_delivered_with_delivery_date": not_delivered_has_date,
        "orders_without_review": no_review,
    }


def customer_identity(con) -> dict:
    """The customer key question: per-order id vs per-person id."""
    c = t("dim_customers")
    dist = rows(con, f"""
        SELECT n_customer_ids AS ids_per_person, count(*) AS people
        FROM {c} GROUP BY 1 ORDER BY 1 DESC
    """)
    people = one(con, f"SELECT count(*) FROM {c}")[0]
    multi = sum(d["people"] for d in dist if d["ids_per_person"] > 1)
    return {
        "people": people,
        "people_with_multiple_order_ids": multi,
        "max_order_ids_for_one_person": max(d["ids_per_person"] for d in dist),
        "distribution": dist,
    }


def repeat_behaviour(con) -> dict:
    o = t("fact_orders")
    seg = rows(con, f"""
        WITH per_customer AS (
            SELECT customer_sk, count(*) AS orders, sum(gmv_items) AS gmv
            FROM {o} o WHERE {DELIVERED} GROUP BY 1
        )
        SELECT CASE WHEN orders = 1 THEN 'one_time' ELSE 'repeat' END AS segment,
               count(*) AS customers,
               round(avg(gmv), 2) AS avg_lifetime_gmv,
               round(avg(gmv / orders), 2) AS avg_per_order
        FROM per_customer GROUP BY 1 ORDER BY 1
    """)
    total = sum(s["customers"] for s in seg)
    rep = next((s for s in seg if s["segment"] == "repeat"), None)
    return {
        "segments": seg,
        "repeat_rate": round(rep["customers"] / total, 4) if rep and total else None,
    }


def delivery_and_reviews(con) -> dict:
    """The chain that carries the recommendation: distance, lateness, rating."""
    o, c = t("fact_orders"), t("dim_customers")
    national = one(con, f"""
        SELECT round(avg(date_diff('day', order_purchase_timestamp, order_delivered_customer_date)), 1),
               round(100.0 * count(*) FILTER (WHERE delivered_on_time = false) / count(*), 1)
        FROM {o} o WHERE {DELIVERED} AND order_delivered_customer_date IS NOT NULL
    """)
    on_time_split = rows(con, f"""
        SELECT delivered_on_time, count(*) AS orders,
               round(avg(review_score_avg), 2) AS avg_review,
               round(100.0 * count(*) FILTER (WHERE review_score_avg <= 2) / count(*), 1) AS pct_one_or_two_star
        FROM {o} o
        WHERE {DELIVERED} AND delivered_on_time IS NOT NULL AND review_score_avg IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)
    lateness = rows(con, f"""
        WITH d AS (
            SELECT date_diff('day', order_estimated_delivery_date, order_delivered_customer_date) AS late_days,
                   review_score_avg AS review
            FROM {o} o WHERE {DELIVERED} AND order_delivered_customer_date IS NOT NULL
        )
        SELECT CASE WHEN late_days <= 0 THEN '0 on time or early'
                    WHEN late_days <= 7 THEN '1 to 7 days late'
                    WHEN late_days <= 30 THEN '8 to 30 days late'
                    ELSE 'over 30 days late' END AS bucket,
               count(*) AS orders,
               count(*) FILTER (WHERE review IS NULL) AS without_review,
               round(avg(review), 2) AS avg_review,
               round(100.0 * count(*) FILTER (WHERE review <= 2) / count(*) FILTER (WHERE review IS NOT NULL), 1) AS pct_one_or_two_star
        FROM d GROUP BY 1 ORDER BY 1
    """)
    by_state = rows(con, f"""
        SELECT c.state, count(*) AS orders,
               round(avg(date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 1) AS avg_days_to_deliver,
               round(100.0 * count(*) FILTER (WHERE o.delivered_on_time = false) / count(*), 1) AS pct_late,
               round(avg(o.review_score_avg), 2) AS avg_review,
               round(100.0 * sum(o.freight_total) / sum(o.gmv_items), 1) AS freight_pct_of_gmv
        FROM {o} o JOIN {c} c ON o.customer_sk = c.customer_sk
        WHERE {DELIVERED} AND o.order_delivered_customer_date IS NOT NULL
        GROUP BY 1 HAVING count(*) >= 500 ORDER BY avg_days_to_deliver
    """)
    return {
        "national_avg_days_to_deliver": national[0],
        "national_pct_late": national[1],
        "on_time_vs_late": on_time_split,
        "lateness_buckets": lateness,
        "by_state_min_500_orders": by_state,
    }


def review_timing(con) -> dict:
    """When the survey goes out, relative to the promise and to the delivery.

    Needs the raw reviews file, because the star schema keeps the score but not
    the review timestamp. This is what explains the shape of the lateness curve.
    """
    raw = Path("lake/raw/olist/olist_order_reviews_dataset.csv")
    if not raw.exists():
        return {"available": False, "reason": f"{raw} not found"}
    o = t("fact_orders")
    base = f"""
        WITH r AS (SELECT order_id, review_score, review_creation_date FROM read_csv_auto('{raw}')),
        d AS (
            SELECT o.order_id, r.review_score, r.review_creation_date,
                   date_diff('day', o.order_estimated_delivery_date, o.order_delivered_customer_date) AS late_days,
                   date_diff('day', o.order_purchase_timestamp, r.review_creation_date) AS days_waited_at_review,
                   date_diff('day', o.order_estimated_delivery_date, r.review_creation_date) AS review_vs_promise,
                   date_diff('day', r.review_creation_date, o.order_delivered_customer_date) AS delivery_after_review
            FROM {o} o JOIN r ON o.order_id = r.order_id
            WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
        ),
        b AS (
            SELECT *, CASE WHEN late_days <= 0 THEN '0 on time or early'
                           WHEN late_days <= 7 THEN '1 to 7 days late'
                           WHEN late_days <= 30 THEN '8 to 30 days late'
                           ELSE 'over 30 days late' END AS bucket
            FROM d
        )
    """
    by_bucket = rows(con, base + """
        SELECT bucket, count(*) AS orders,
               round(avg(review_vs_promise), 1) AS avg_days_survey_after_promise,
               round(avg(days_waited_at_review), 1) AS avg_days_waited_when_rated,
               round(100.0 * count(*) FILTER (WHERE delivery_after_review > 0) / count(*), 1) AS pct_rated_before_delivery,
               round(avg(late_days), 1) AS avg_final_lateness,
               round(avg(review_score), 2) AS avg_score
        FROM b GROUP BY 1 ORDER BY 1
    """)
    return {"available": True, "by_bucket": by_bucket}


def concentration(con) -> dict:
    o, i, p = t("fact_orders"), t("fact_order_items"), t("dim_products")
    cat = rows(con, f"""
        SELECT p.category_en AS category, round(sum(i.price), 0) AS gmv,
               round(100.0 * sum(i.price) / sum(sum(i.price)) OVER (), 2) AS pct_of_gmv
        FROM {i} i JOIN {p} p ON i.product_sk = p.product_sk JOIN {o} o ON i.order_id = o.order_id
        WHERE {DELIVERED} GROUP BY 1 ORDER BY gmv DESC LIMIT 10
    """)
    sellers = one(con, f"""
        WITH s AS (SELECT seller_sk, sum(price) AS gmv FROM {i} GROUP BY 1),
             r AS (SELECT *, row_number() OVER (ORDER BY gmv DESC) AS rnk FROM s)
        SELECT count(*), round(100.0 * sum(gmv) FILTER (WHERE rnk <= 10) / sum(gmv), 1),
               round(100.0 * sum(gmv) FILTER (WHERE rnk <= 100) / sum(gmv), 1) FROM r
    """)
    geo = rows(con, f"""
        SELECT c.state, count(*) AS orders, round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct_of_orders
        FROM {o} o JOIN {t('dim_customers')} c ON o.customer_sk = c.customer_sk
        WHERE {DELIVERED} GROUP BY 1 ORDER BY orders DESC LIMIT 6
    """)
    return {
        "top_categories": cat,
        "top10_categories_share": round(sum(c["pct_of_gmv"] for c in cat), 1),
        "sellers_total": sellers[0],
        "top10_sellers_share": sellers[1],
        "top100_sellers_share": sellers[2],
        "top_states_by_orders": geo,
    }


def order_value(con) -> dict:
    o = t("fact_orders")
    mean, med, mx = one(con, f"""
        SELECT round(avg(gmv_items), 2), round(median(gmv_items), 2), round(max(gmv_items), 2)
        FROM {o} o WHERE {DELIVERED}
    """)
    pay = rows(con, f"""
        SELECT payment_type_primary AS payment_type, count(*) AS orders,
               round(avg(payment_value_total), 2) AS avg_payment
        FROM {o} o WHERE {DELIVERED} GROUP BY 1 ORDER BY orders DESC
    """)
    return {"mean_order_gmv": mean, "median_order_gmv": med, "max_order_gmv": mx,
            "mean_over_median": round(mean / med, 2), "payment_mix": pay}


def main() -> int:
    global STAR
    ap = argparse.ArgumentParser(description="Insight layer over the processed star schema")
    ap.add_argument("--star-dir", type=Path, default=STAR)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    STAR = args.star_dir
    if not (STAR / "fact_orders.parquet").exists():
        print(f"No star schema at {STAR}. Run `python -m src.run_pipeline --skip-s3` first.")
        return 1

    con = duckdb.connect()
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "star_dir": str(STAR),
        "delivered_filter": "order_status = 'delivered'",
        "coverage": coverage(con),
        "integrity": integrity(con),
        "customer_identity": customer_identity(con),
        "repeat_behaviour": repeat_behaviour(con),
        "delivery_and_reviews": delivery_and_reviews(con),
        "review_timing": review_timing(con),
        "concentration": concentration(con),
        "order_value": order_value(con),
    }
    con.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    cov, integ, ident = report["coverage"], report["integrity"], report["customer_identity"]
    dr, con_, val = report["delivery_and_reviews"], report["concentration"], report["order_value"]
    print("COVERAGE")
    print(f"  window        {cov['first_order'][:10]} to {cov['last_order'][:10]}")
    print(f"  missing       {cov['missing_months'] or 'none'}")
    thin = ", ".join("{} ({})".format(m["year_month"], m["orders"]) for m in cov["thin_months"])
    print(f"  thin months   {thin or 'none'}")
    print(f"  reliable      {cov['reliable_window']['start']} to {cov['reliable_window']['end']}")
    print("INTEGRITY")
    print(f"  delivered without a delivery date   {integ['delivered_without_delivery_date']}")
    print(f"  not delivered but has one           {integ['not_delivered_with_delivery_date']}")
    print(f"  orders with no review               {integ['orders_without_review']:,}")
    print("CUSTOMER IDENTITY")
    print(f"  people {ident['people']:,}; with more than one order id {ident['people_with_multiple_order_ids']:,}; max {ident['max_order_ids_for_one_person']}")
    print(f"  repeat rate {report['repeat_behaviour']['repeat_rate']:.1%}")
    print("DELIVERY AND REVIEWS")
    print(f"  national {dr['national_avg_days_to_deliver']} days, {dr['national_pct_late']}% late")
    for b in dr["lateness_buckets"]:
        print(f"  {b['bucket']:<22} n={b['orders']:>6}  review={b['avg_review']}  1-2 star={b['pct_one_or_two_star']}%")
    rt = report["review_timing"]
    if rt.get("available"):
        print("REVIEW TIMING")
        for b in rt["by_bucket"]:
            print(f"  {b['bucket']:<22} survey {b['avg_days_survey_after_promise']:>6}d after promise | "
                  f"waited {b['avg_days_waited_when_rated']:>5}d when rated | "
                  f"rated before delivery {b['pct_rated_before_delivery']:>5}% | "
                  f"final lateness {b['avg_final_lateness']:>6}d | score {b['avg_score']}")
    print("CONCENTRATION")
    print(f"  top 10 categories {con_['top10_categories_share']}% of GMV")
    print(f"  {con_['sellers_total']:,} sellers; top 100 hold {con_['top100_sellers_share']}%")
    print("ORDER VALUE")
    print(f"  mean {val['mean_order_gmv']}  median {val['median_order_gmv']}  ratio {val['mean_over_median']}")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
