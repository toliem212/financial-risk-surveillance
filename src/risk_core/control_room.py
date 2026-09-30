from __future__ import annotations

from typing import Any

import pandas as pd

from src.risk_core.liquidity_stress_controls import SCENARIO_VI
from src.risk_core.metrics import limit_status, limit_utilization


STATUS_VI = {
    "NORMAL": "BÌNH THƯỜNG",
    "WATCH": "THEO DÕI",
    "WARNING": "CẢNH BÁO",
    "BREACH": "VƯỢT HẠN MỨC",
    "NOT_AVAILABLE": "CHƯA CÓ DỮ LIỆU",
}

STATUS_PRIORITY = {
    "BREACH": 0,
    "WARNING": 1,
    "WATCH": 2,
    "NORMAL": 3,
    "NOT_AVAILABLE": 4,
}

METRIC_VI = {
    "FX_USD_NOP_MN": "Trạng thái mở USD",
    "FX_STRESS_LOSS_BN": "Tổn thất FX dưới stress",
    "RATES_PV01_BN_PER_BP": "PV01 danh mục TPCP",
    "RATES_STRESS_LOSS_BN": "Tổn thất lãi suất dưới stress",
    "LIQ_CUM_GAP_7D_BN": "GAP thanh khoản 7 ngày",
    "LIQ_CUM_GAP_30D_BN": "GAP thanh khoản 30 ngày",
}

STRESS_CONTROL_VI = {
    "FX stress": "FX",
    "Rates stress": "Lãi suất",
    "Liquidity 7D": "Thanh khoản 7D",
    "Liquidity 30D": "Thanh khoản 30D",
}

ACTION_MAP = {
    "FX_USD_NOP_MN": "Rà soát trạng thái ngoại tệ và nhu cầu hedge.",
    "FX_STRESS_LOSS_BN": "Rà soát NOP, driver tỷ giá và hiệu quả hedge.",
    "RATES_PV01_BN_PER_BP": "Rà soát PV01 theo tenor và khả năng giảm duration.",
    "RATES_STRESS_LOSS_BN": "Rà soát exposure lãi suất và mức lỗ dưới stress.",
    "LIQ_CUM_GAP_7D_BN": "Rà soát dòng tiền 7 ngày và phương án funding dự phòng.",
    "LIQ_CUM_GAP_30D_BN": "Rà soát dòng tiền 30 ngày và kế hoạch funding.",
}


def _limit_map(snapshot: dict) -> dict[str, float]:
    limits = snapshot.get("limits")
    if not isinstance(limits, pd.DataFrame) or limits.empty:
        return {}

    out: dict[str, float] = {}
    for row in limits.to_dict("records"):
        metric_id = str(row.get("metric_id") or "")
        value = pd.to_numeric(row.get("limit_value"), errors="coerce")
        if metric_id and not pd.isna(value):
            out[metric_id] = float(value)
    return out


def base_limit_control_table(snapshot: dict) -> pd.DataFrame:
    limits = snapshot.get("limits")
    if not isinstance(limits, pd.DataFrame) or limits.empty:
        return pd.DataFrame()

    out = limits.copy()
    out["control_name"] = out["metric_id"].astype(str).map(METRIC_VI).fillna(
        out["metric_id"].astype(str)
    )
    out["status_vi"] = out["status"].astype(str).map(STATUS_VI).fillna(
        out["status"].astype(str)
    )
    out["action"] = out["metric_id"].astype(str).map(ACTION_MAP).fillna(
        "Rà soát driver và exposure liên quan."
    )
    out["_priority"] = out["status"].astype(str).map(STATUS_PRIORITY).fillna(9)
    out = out.sort_values(
        ["_priority", "utilization_pct"],
        ascending=[True, False],
        na_position="last",
    ).drop(columns=["_priority"])
    return out.reset_index(drop=True)


def _merge_scenarios(snapshot: dict) -> pd.DataFrame:
    fx = snapshot.get("fx_stress")
    rates = snapshot.get("rate_stress")
    liq = snapshot.get("liquidity_stress")

    frames = []
    if isinstance(fx, pd.DataFrame) and not fx.empty:
        frames.append(
            fx[["scenario_id", "fx_usd_vnd_shock_pct", "fx_loss_bn_vnd"]].copy()
        )
    if isinstance(rates, pd.DataFrame) and not rates.empty:
        frames.append(
            rates[["scenario_id", "rates_parallel_bp", "rates_loss_bn_vnd"]].copy()
        )
    if isinstance(liq, pd.DataFrame) and not liq.empty:
        frames.append(
            liq[
                [
                    "scenario_id",
                    "liquidity_outflow_addon_pct",
                    "stressed_gap_7d_bn_vnd",
                    "stressed_gap_30d_bn_vnd",
                ]
            ].copy()
        )

    if not frames:
        return pd.DataFrame()

    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="scenario_id", how="outer")
    return out


def stress_control_table(snapshot: dict) -> pd.DataFrame:
    scenarios = _merge_scenarios(snapshot)
    if scenarios.empty:
        return pd.DataFrame()

    limits = _limit_map(snapshot)
    rows: list[dict[str, Any]] = []

    for row in scenarios.to_dict("records"):
        scenario_id = str(row.get("scenario_id") or "")
        fx_loss = pd.to_numeric(row.get("fx_loss_bn_vnd"), errors="coerce")
        rates_loss = pd.to_numeric(row.get("rates_loss_bn_vnd"), errors="coerce")
        gap_7d = pd.to_numeric(row.get("stressed_gap_7d_bn_vnd"), errors="coerce")
        gap_30d = pd.to_numeric(row.get("stressed_gap_30d_bn_vnd"), errors="coerce")

        fx_util = None if pd.isna(fx_loss) else limit_utilization(
            float(fx_loss), limits.get("FX_STRESS_LOSS_BN")
        )
        rates_util = None if pd.isna(rates_loss) else limit_utilization(
            float(rates_loss), limits.get("RATES_STRESS_LOSS_BN")
        )
        liq7_util = None if pd.isna(gap_7d) else limit_utilization(
            float(gap_7d), limits.get("LIQ_CUM_GAP_7D_BN")
        )
        liq30_util = None if pd.isna(gap_30d) else limit_utilization(
            float(gap_30d), limits.get("LIQ_CUM_GAP_30D_BN")
        )

        statuses = {
            "FX stress": limit_status(fx_util),
            "Rates stress": limit_status(rates_util),
            "Liquidity 7D": limit_status(liq7_util),
            "Liquidity 30D": limit_status(liq30_util),
        }

        breach_controls = [
            name for name, status in statuses.items() if status == "BREACH"
        ]
        attention_controls = [
            name for name, status in statuses.items()
            if status in {"WATCH", "WARNING"}
        ]

        util_values = [
            float(v)
            for v in [fx_util, rates_util, liq7_util, liq30_util]
            if v is not None
        ]
        max_util = max(util_values) if util_values else None

        market_loss = None
        if not pd.isna(fx_loss) or not pd.isna(rates_loss):
            market_loss = (
                (0.0 if pd.isna(fx_loss) else float(fx_loss))
                + (0.0 if pd.isna(rates_loss) else float(rates_loss))
            )

        if breach_controls:
            conclusion = "Vượt: " + ", ".join(
                STRESS_CONTROL_VI.get(x, x) for x in breach_controls
            )
        elif attention_controls:
            conclusion = "Theo dõi: " + ", ".join(
                STRESS_CONTROL_VI.get(x, x) for x in attention_controls
            )
        else:
            conclusion = "Trong hạn mức"

        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": SCENARIO_VI.get(
                    scenario_id, scenario_id or "Kịch bản"
                ),
                "shock_summary": (
                    f"FX {float(row.get('fx_usd_vnd_shock_pct') or 0):+.1f}% · "
                    f"LS +{float(row.get('rates_parallel_bp') or 0):.0f}bp · "
                    f"Outflow +{float(row.get('liquidity_outflow_addon_pct') or 0):.0f}%"
                ),
                "fx_shock_pct": pd.to_numeric(
                    row.get("fx_usd_vnd_shock_pct"), errors="coerce"
                ),
                "rates_shock_bp": pd.to_numeric(
                    row.get("rates_parallel_bp"), errors="coerce"
                ),
                "liquidity_outflow_addon_pct": pd.to_numeric(
                    row.get("liquidity_outflow_addon_pct"), errors="coerce"
                ),
                "market_loss_bn_vnd": market_loss,
                "fx_utilization_pct": fx_util,
                "rates_utilization_pct": rates_util,
                "liq_7d_utilization_pct": liq7_util,
                "liq_30d_utilization_pct": liq30_util,
                "breach_count": len(breach_controls),
                "breach_controls": ", ".join(breach_controls),
                "max_utilization_pct": max_util,
                "conclusion": conclusion,
            }
        )

    return pd.DataFrame(rows).sort_values(
        "liquidity_outflow_addon_pct", na_position="last"
    ).reset_index(drop=True)


def control_room_summary(snapshot: dict) -> dict:
    base = base_limit_control_table(snapshot)
    stress = stress_control_table(snapshot)

    base_breach = (
        int(base["status"].astype(str).eq("BREACH").sum()) if not base.empty else 0
    )
    base_attention = (
        int(base["status"].astype(str).isin(["WATCH", "WARNING"]).sum())
        if not base.empty else 0
    )

    first_breach = None
    if not stress.empty:
        breached = stress[stress["breach_count"] > 0]
        if not breached.empty:
            first_breach = breached.iloc[0]

    highest = None
    if not base.empty:
        valid = base[pd.to_numeric(base["utilization_pct"], errors="coerce").notna()]
        if not valid.empty:
            highest = valid.sort_values("utilization_pct", ascending=False).iloc[0]

    return {
        "base_breach_count": base_breach,
        "base_attention_count": base_attention,
        "highest_base_control": None if highest is None else str(highest["control_name"]),
        "highest_base_utilization_pct": (
            None if highest is None else float(highest["utilization_pct"])
        ),
        "first_stress_breach_scenario": (
            None if first_breach is None else str(first_breach["scenario_label"])
        ),
        "first_stress_breach_id": (
            None if first_breach is None else str(first_breach["scenario_id"])
        ),
        "first_stress_breach_controls": (
            None if first_breach is None else str(first_breach["breach_controls"])
        ),
        "max_stress_breach_count": (
            0 if stress.empty else int(stress["breach_count"].max())
        ),
    }


def action_queue(snapshot: dict) -> pd.DataFrame:
    base = base_limit_control_table(snapshot)
    stress = stress_control_table(snapshot)
    rows: list[dict[str, Any]] = []

    if not stress.empty:
        breached = stress[stress["breach_count"] > 0]
        if not breached.empty:
            first = breached.iloc[0]
            rows.append(
                {
                    "priority": "KHẨN",
                    "issue": "Vượt hạn mức dưới stress",
                    "trigger": (
                        f"{first['scenario_label']}: "
                        + ", ".join(
                            STRESS_CONTROL_VI.get(x.strip(), x.strip())
                            for x in str(first["breach_controls"]).split(",")
                            if x.strip()
                        )
                    ),
                    "action": (
                        "Xác nhận dữ liệu; rà soát exposure, hedge/funding; "
                        "chuẩn bị phương án contingency và escalation."
                    ),
                    "source": "Stress testing",
                }
            )

    if not base.empty:
        for row in base.to_dict("records"):
            status = str(row.get("status") or "")
            if status not in {"WATCH", "WARNING", "BREACH"}:
                continue
            priority = (
                "KHẨN" if status == "BREACH"
                else "CAO" if status == "WARNING"
                else "THEO DÕI"
            )
            rows.append(
                {
                    "priority": priority,
                    "issue": str(row.get("control_name") or ""),
                    "trigger": (
                        f"{float(row['utilization_pct']):.1f}% hạn mức · "
                        f"{STATUS_VI.get(status, status)}"
                    ),
                    "action": str(row.get("action") or ""),
                    "source": "Trạng thái cơ sở",
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=["priority", "issue", "trigger", "action", "source"]
        )

    order = {"KHẨN": 0, "CAO": 1, "THEO DÕI": 2}
    out = pd.DataFrame(rows)
    out["_order"] = out["priority"].map(order).fillna(9)
    return out.sort_values(["_order", "issue"]).drop(
        columns=["_order"]
    ).reset_index(drop=True)


def management_insights(snapshot: dict) -> list[str]:
    summary = control_room_summary(snapshot)
    base = base_limit_control_table(snapshot)
    stress = stress_control_table(snapshot)
    insights: list[str] = []

    if summary["base_breach_count"] == 0:
        insights.append(
            f"Trạng thái cơ sở chưa có hạn mức bị vượt; "
            f"{summary['base_attention_count']} chỉ tiêu đang ở vùng theo dõi/cảnh báo."
        )
    else:
        insights.append(
            f"Trạng thái cơ sở có {summary['base_breach_count']} hạn mức bị vượt "
            f"và {summary['base_attention_count']} chỉ tiêu ở vùng theo dõi/cảnh báo."
        )

    if summary["highest_base_control"] is not None:
        insights.append(
            f"Chỉ tiêu gần hạn mức nhất hiện là "
            f"**{summary['highest_base_control']}** ở "
            f"{summary['highest_base_utilization_pct']:.1f}%."
        )

    if summary["first_stress_breach_scenario"] is not None:
        controls_vi = ", ".join(
            STRESS_CONTROL_VI.get(x.strip(), x.strip())
            for x in str(summary["first_stress_breach_controls"]).split(",")
            if x.strip()
        )
        insights.append(
            f"Vượt hạn mức đầu tiên xuất hiện ở kịch bản "
            f"**{summary['first_stress_breach_scenario']}**, tác động đến {controls_vi}."
        )

    if not stress.empty:
        extreme = stress.iloc[-1]
        if int(extreme["breach_count"]) > 0:
            insights.append(
                f"Ở kịch bản stress cao nhất, "
                f"{int(extreme['breach_count'])}/4 kiểm soát stress bị vượt; "
                f"mức sử dụng cao nhất đạt {float(extreme['max_utilization_pct']):.1f}%."
            )

    if not base.empty:
        rate_rows = base[
            base["metric_id"].astype(str).isin(
                ["RATES_PV01_BN_PER_BP", "RATES_STRESS_LOSS_BN"]
            )
        ]
        if (
            len(rate_rows) == 2
            and rate_rows["status"].astype(str).eq("WATCH").all()
        ):
            insights.append(
                "Cả PV01 và tổn thất lãi suất dưới stress đều đang ở vùng THEO DÕI, "
                "cho thấy rủi ro lãi suất là cụm cần giám sát sát hơn trong trạng thái cơ sở."
            )

    return insights
