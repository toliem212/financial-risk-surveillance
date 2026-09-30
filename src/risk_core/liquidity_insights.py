from __future__ import annotations

from typing import Any

import pandas as pd


STATUS_VI = {
    "NORMAL": "BÌNH THƯỜNG",
    "WATCH": "THEO DÕI",
    "WARNING": "CẢNH BÁO",
    "BREACH": "VƯỢT HẠN MỨC",
    "NOT_AVAILABLE": "CHƯA CÓ DỮ LIỆU",
}


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _liquidity_limits(snapshot: dict) -> pd.DataFrame:
    limits = snapshot.get("limits")
    if not isinstance(limits, pd.DataFrame) or limits.empty:
        return pd.DataFrame()
    return limits[
        limits["metric_id"].astype(str).isin(
            ["LIQ_CUM_GAP_7D_BN", "LIQ_CUM_GAP_30D_BN"]
        )
    ].copy()


def liquidity_limit_summary(snapshot: dict) -> dict:
    liq_limits = _liquidity_limits(snapshot)
    if liq_limits.empty:
        return {
            "max_utilization_pct": None,
            "status": "NOT_AVAILABLE",
            "status_vi": STATUS_VI["NOT_AVAILABLE"],
        }

    util = pd.to_numeric(liq_limits["utilization_pct"], errors="coerce")
    valid = liq_limits.loc[util.notna()].copy()
    if valid.empty:
        return {
            "max_utilization_pct": None,
            "status": "NOT_AVAILABLE",
            "status_vi": STATUS_VI["NOT_AVAILABLE"],
        }

    valid["_util"] = pd.to_numeric(valid["utilization_pct"], errors="coerce")
    row = valid.sort_values("_util", ascending=False).iloc[0]
    status = str(row.get("status") or "NOT_AVAILABLE")
    return {
        "max_utilization_pct": float(row["_util"]),
        "status": status,
        "status_vi": STATUS_VI.get(status, status),
        "metric_id": str(row.get("metric_id") or ""),
    }


def worst_liquidity_stress(snapshot: dict) -> dict:
    stress = snapshot.get("liquidity_stress")
    if not isinstance(stress, pd.DataFrame) or stress.empty:
        return {
            "scenario_id": None,
            "scenario_name": None,
            "addon_pct": None,
            "gap_7d_bn": None,
            "gap_30d_bn": None,
        }

    df = stress.copy()
    df["_addon"] = pd.to_numeric(
        df["liquidity_outflow_addon_pct"], errors="coerce"
    )
    df = df[df["_addon"].notna()]
    if df.empty:
        return {
            "scenario_id": None,
            "scenario_name": None,
            "addon_pct": None,
            "gap_7d_bn": None,
            "gap_30d_bn": None,
        }

    row = df.sort_values("_addon", ascending=False).iloc[0]
    return {
        "scenario_id": str(row.get("scenario_id") or ""),
        "scenario_name": str(row.get("scenario_name") or ""),
        "addon_pct": float(row["_addon"]),
        "gap_7d_bn": _num(row.get("stressed_gap_7d_bn_vnd")),
        "gap_30d_bn": _num(row.get("stressed_gap_30d_bn_vnd")),
    }


def build_liquidity_insights(snapshot: dict) -> list[str]:
    gap_7d = _num(snapshot.get("cumulative_gap_7d_bn_vnd"))
    gap_30d = _num(snapshot.get("cumulative_gap_30d_bn_vnd"))
    insights: list[str] = []

    if gap_7d is not None:
        if gap_7d < 0:
            insights.append(
                f"Trong 7 ngày, dòng tiền ra lũy kế vượt dòng tiền vào "
                f"{abs(gap_7d):,.0f} tỷ VND."
            )
        elif gap_7d > 0:
            insights.append(
                f"Trong 7 ngày, dòng tiền vào lũy kế cao hơn dòng tiền ra "
                f"{gap_7d:,.0f} tỷ VND."
            )
        else:
            insights.append("Cumulative GAP 7 ngày đang cân bằng.")

    if gap_7d is not None and gap_30d is not None:
        change = gap_30d - gap_7d
        if gap_7d < 0 and gap_30d > gap_7d:
            insights.append(
                f"Đến 30 ngày, GAP cải thiện {change:,.0f} tỷ VND so với mốc 7 ngày, "
                f"còn {gap_30d:,.0f} tỷ VND."
            )
        elif gap_30d < gap_7d:
            insights.append(
                f"Đến 30 ngày, GAP xấu thêm {abs(change):,.0f} tỷ VND so với mốc 7 ngày, "
                f"xuống {gap_30d:,.0f} tỷ VND."
            )

    worst = worst_liquidity_stress(snapshot)
    if worst["gap_30d_bn"] is not None and gap_30d is not None:
        deterioration = worst["gap_30d_bn"] - gap_30d
        insights.append(
            f"Kịch bản stress cao nhất (+{worst['addon_pct']:,.0f}% dòng tiền ra) "
            f"đưa GAP 30 ngày xuống {worst['gap_30d_bn']:,.0f} tỷ VND, "
            f"xấu đi {abs(deterioration):,.0f} tỷ VND so với cơ sở."
        )

    limit = liquidity_limit_summary(snapshot)
    util = limit["max_utilization_pct"]
    if util is not None:
        insights.append(
            f"Mức sử dụng hạn mức thanh khoản cao nhất hiện là {util:,.1f}% "
            f"— {limit['status_vi']}."
        )

    market = snapshot.get("market") or {}
    on_rate = _num((market.get("ibor_vnd_on") or {}).get("rate_pct"))
    omo_net = _num(market.get("omo_net"))
    if on_rate is not None or omo_net is not None:
        parts = []
        if on_rate is not None:
            parts.append(f"O/N VND {on_rate:,.2f}%")
        if omo_net is not None:
            direction = "bơm ròng" if omo_net > 0 else "hút ròng" if omo_net < 0 else "cân bằng"
            parts.append(f"OMO {direction} {abs(omo_net):,.0f} tỷ VND")
        insights.append(
            "Bối cảnh thị trường tiền tệ: " + " · ".join(parts) + "."
        )

    return insights
