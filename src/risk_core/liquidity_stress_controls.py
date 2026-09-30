from __future__ import annotations

import pandas as pd

from src.risk_core.liquidity_insights import STATUS_VI
from src.risk_core.metrics import limit_status, limit_utilization


SCENARIO_VI = {
    "MILD": "Căng thẳng vừa",
    "MODERATE": "Căng thẳng vừa",
    "SEVERE": "Căng thẳng mạnh",
    "EXTREME": "Căng thẳng cực đoan",
}


def _limit_value(snapshot: dict, metric_id: str) -> float | None:
    limits = snapshot.get("limits")
    if not isinstance(limits, pd.DataFrame) or limits.empty:
        return None

    hit = limits[limits["metric_id"].astype(str).eq(metric_id)]
    if hit.empty:
        return None

    value = pd.to_numeric(hit.iloc[0].get("limit_value"), errors="coerce")
    return None if pd.isna(value) else float(value)


def liquidity_stress_limit_table(snapshot: dict) -> pd.DataFrame:
    stress = snapshot.get("liquidity_stress")
    if not isinstance(stress, pd.DataFrame) or stress.empty:
        return pd.DataFrame()

    limit_7d = _limit_value(snapshot, "LIQ_CUM_GAP_7D_BN")
    limit_30d = _limit_value(snapshot, "LIQ_CUM_GAP_30D_BN")

    rows = []
    for row in stress.to_dict("records"):
        gap_7d = float(row["stressed_gap_7d_bn_vnd"])
        gap_30d = float(row["stressed_gap_30d_bn_vnd"])
        util_7d = limit_utilization(gap_7d, limit_7d)
        util_30d = limit_utilization(gap_30d, limit_30d)
        status_7d = limit_status(util_7d)
        status_30d = limit_status(util_30d)

        scenario_id = str(row.get("scenario_id") or "")
        addon = float(row["liquidity_outflow_addon_pct"])

        rows.append({
            "scenario_id": scenario_id,
            "scenario_label": SCENARIO_VI.get(
                scenario_id,
                f"Stress +{addon:.0f}% dòng tiền ra",
            ),
            "liquidity_outflow_addon_pct": addon,
            "stressed_gap_7d_bn_vnd": gap_7d,
            "stressed_gap_30d_bn_vnd": gap_30d,
            "utilization_7d_pct": util_7d,
            "utilization_30d_pct": util_30d,
            "status_7d": status_7d,
            "status_30d": status_30d,
            "status_7d_vi": STATUS_VI.get(status_7d, status_7d),
            "status_30d_vi": STATUS_VI.get(status_30d, status_30d),
        })

    return pd.DataFrame(rows).sort_values(
        "liquidity_outflow_addon_pct"
    ).reset_index(drop=True)


def stress_control_summary(snapshot: dict) -> dict:
    table = liquidity_stress_limit_table(snapshot)
    if table.empty:
        return {
            "first_watch_addon_pct": None,
            "first_breach_addon_pct": None,
            "first_breach_horizons": [],
            "severe_util_7d_pct": None,
            "severe_util_30d_pct": None,
        }

    watched = table[
        table["status_7d"].astype(str).isin(["WATCH", "WARNING"])
        | table["status_30d"].astype(str).isin(["WATCH", "WARNING"])
    ]
    breached = table[
        table["status_7d"].astype(str).eq("BREACH")
        | table["status_30d"].astype(str).eq("BREACH")
    ]

    first_watch = None if watched.empty else watched.iloc[0]
    first_breach = None if breached.empty else breached.iloc[0]

    horizons: list[str] = []
    if first_breach is not None:
        if str(first_breach["status_7d"]) == "BREACH":
            horizons.append("7D")
        if str(first_breach["status_30d"]) == "BREACH":
            horizons.append("30D")

    severe = table.iloc[-1]
    return {
        "first_watch_addon_pct": (
            None if first_watch is None
            else float(first_watch["liquidity_outflow_addon_pct"])
        ),
        "first_breach_addon_pct": (
            None if first_breach is None
            else float(first_breach["liquidity_outflow_addon_pct"])
        ),
        "first_breach_horizons": horizons,
        "severe_util_7d_pct": float(severe["utilization_7d_pct"]),
        "severe_util_30d_pct": float(severe["utilization_30d_pct"]),
    }


def stress_limit_insights(snapshot: dict) -> list[str]:
    table = liquidity_stress_limit_table(snapshot)
    summary = stress_control_summary(snapshot)
    if table.empty:
        return []

    insights: list[str] = []

    watch_addon = summary["first_watch_addon_pct"]
    if watch_addon is not None:
        row = table[
            table["liquidity_outflow_addon_pct"].eq(watch_addon)
        ].iloc[0]
        parts = []
        if str(row["status_7d"]) in {"WATCH", "WARNING"}:
            parts.append(
                f"7D {float(row['utilization_7d_pct']):.1f}% "
                f"({row['status_7d_vi']})"
            )
        if str(row["status_30d"]) in {"WATCH", "WARNING"}:
            parts.append(
                f"30D {float(row['utilization_30d_pct']):.1f}% "
                f"({row['status_30d_vi']})"
            )
        if parts:
            insights.append(
                f"Từ stress +{watch_addon:.0f}% dòng tiền ra, "
                "mức sử dụng hạn mức bắt đầu đi vào vùng theo dõi: "
                + ", ".join(parts) + "."
            )

    breach_addon = summary["first_breach_addon_pct"]
    if breach_addon is not None:
        row = table[
            table["liquidity_outflow_addon_pct"].eq(breach_addon)
        ].iloc[0]
        parts = []
        if str(row["status_7d"]) == "BREACH":
            parts.append(f"7D {float(row['utilization_7d_pct']):.1f}%")
        if str(row["status_30d"]) == "BREACH":
            parts.append(f"30D {float(row['utilization_30d_pct']):.1f}%")
        insights.append(
            f"Ngưỡng vượt hạn mức xuất hiện từ stress +{breach_addon:.0f}% dòng tiền ra: "
            + ", ".join(parts) + "."
        )

    severe = table.iloc[-1]
    if (
        str(severe["status_7d"]) == "BREACH"
        or str(severe["status_30d"]) == "BREACH"
    ):
        breached = []
        if str(severe["status_7d"]) == "BREACH":
            breached.append(f"7D {float(severe['utilization_7d_pct']):.1f}%")
        if str(severe["status_30d"]) == "BREACH":
            breached.append(f"30D {float(severe['utilization_30d_pct']):.1f}%")
        insights.append(
            f"Ở stress cao nhất +{float(severe['liquidity_outflow_addon_pct']):.0f}%, "
            "mức sử dụng hạn mức tăng lên " + ", ".join(breached) + "."
        )

    return insights
