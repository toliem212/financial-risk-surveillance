from __future__ import annotations

from typing import Any

import pandas as pd


SEVERITY_PRIORITY = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "INFO": 4,
}

SEVERITY_VI = {
    "CRITICAL": "NGHIÊM TRỌNG",
    "HIGH": "CAO",
    "MEDIUM": "TRUNG BÌNH",
    "LOW": "THẤP",
    "INFO": "THÔNG TIN",
}

DOMAIN_VI = {
    "LIQUIDITY": "Thanh khoản",
    "FX": "Ngoại hối",
    "RATES": "Lãi suất / TPCP",
    "CORPORATE_BOND": "Trái phiếu doanh nghiệp",
    "DATA_QUALITY": "Chất lượng dữ liệu",
}

STATUS_VI = {
    "OPEN": "ĐANG MỞ",
    "CLOSED": "ĐÃ ĐÓNG",
    "ACKNOWLEDGED": "ĐÃ XÁC NHẬN",
    "INVESTIGATING": "ĐANG ĐIỀU TRA",
    "ESCALATED": "ĐÃ ESCALATE",
    "RESOLVED": "ĐÃ XỬ LÝ",
}

DQ_VI = {
    "OK": "ĐẠT",
    "CAUTION": "CẦN LƯU Ý",
    "REVIEW": "CẦN XÁC MINH",
}

TRANSMISSION_VI = {
    "LIQUIDITY": [
        "Căng thẳng vốn ngắn hạn có thể truyền sang lãi suất liên ngân hàng theo kỳ hạn và chi phí vốn.",
        "Nếu áp lực thanh khoản kéo dài, cần đọc cùng diễn biến FX và lợi suất TPCP để kiểm tra mức độ lan truyền.",
    ],
    "FX": [
        "Biến động USD/VND có thể làm thay đổi valuation và rủi ro của trạng thái ngoại hối mở.",
        "Cần đọc cùng O/N, term rates và OMO để kiểm tra liệu áp lực FX có đi kèm căng thẳng thanh khoản hay không.",
    ],
    "RATES": [
        "Biến động lợi suất làm thay đổi valuation và PV01/DV01 của danh mục trái phiếu.",
        "Cần phân biệt tín hiệu từ giao dịch thứ cấp với kết quả đấu thầu sơ cấp khi đánh giá cung - cầu.",
    ],
    "CORPORATE_BOND": [
        "Sự kiện trái phiếu có thể làm thay đổi bối cảnh thanh khoản, tái cấp vốn, kỳ hạn hoặc điều khoản của issuer/bond liên quan.",
        "Cần đọc cùng thanh khoản giao dịch, thời gian đến đáo hạn và nội dung disclosure cụ thể.",
    ],
    "DATA_QUALITY": [
        "Cần xử lý bất nhất dữ liệu trước khi diễn giải tác động kinh tế.",
        "Mismatch có thể đến từ timing, định nghĩa, đơn vị hoặc parser; không tự động đồng nghĩa với rủi ro thị trường.",
    ],
}

MONITOR_NEXT_VI = {
    "LIQUIDITY": [
        "Kết quả OMO tiếp theo và lịch đáo hạn.",
        "Cấu trúc kỳ hạn O/N - 1W - 1M.",
        "Phản ứng đồng thời của FX và lợi suất TPCP.",
    ],
    "FX": [
        "USD/VND liên ngân hàng ở các quan sát tiếp theo.",
        "Khoảng cách tới các mức tham chiếu điều hành.",
        "O/N/term rates và xác nhận từ thị trường tiền tệ.",
    ],
    "RATES": [
        "Lợi suất 5Y/10Y/15Y và hình dạng đường cong.",
        "Dữ liệu giao dịch thứ cấp so với kết quả đấu thầu sơ cấp.",
        "PV01 và stress loss của danh mục mô phỏng.",
    ],
    "CORPORATE_BOND": [
        "Disclosure tiếp theo của issuer.",
        "Thay đổi trạng thái giao dịch.",
        "Rating/payment/maturity event của cùng issuer hoặc bond.",
    ],
    "DATA_QUALITY": [
        "Xác nhận lại nguồn primary.",
        "Sức khỏe parser/source-run.",
        "Mismatch có tiếp diễn sau lần ingest kế tiếp hay không.",
    ],
}

DOMAIN_ACTIONS = {
    "LIQUIDITY": "Rà soát funding gap, maturity ladder và phương án funding dự phòng.",
    "FX": "Rà soát NOP, valuation, hedge và diễn biến liên ngân hàng.",
    "RATES": "Rà soát PV01 theo tenor, duration và stress loss của danh mục.",
    "CORPORATE_BOND": "Rà soát issuer/bond event, kỳ hạn, điều khoản và mức độ liên quan tới exposure.",
    "DATA_QUALITY": "Xác minh nguồn, timestamp, đơn vị và parser trước khi dùng tín hiệu cho quyết định rủi ro.",
}


def feed_summary(feed: list[dict]) -> dict[str, int]:
    if not feed:
        return {
            "total": 0,
            "signals": 0,
            "high_critical": 0,
            "open_signals": 0,
            "domains": 0,
            "events": 0,
        }

    df = pd.DataFrame(feed)
    item_type = df.get("item_type", pd.Series(dtype=str)).astype(str)
    severity = df.get("severity", pd.Series(dtype=str)).astype(str)

    signal_mask = item_type.eq("SIGNAL")
    event_mask = item_type.eq("EVENT")

    status = df.get("status")
    if status is None:
        open_signals = int(signal_mask.sum())
    else:
        open_signals = int(
            (signal_mask & status.fillna("OPEN").astype(str).str.upper().eq("OPEN")).sum()
        )

    domains = (
        int(df.loc[signal_mask, "domain"].dropna().astype(str).nunique())
        if "domain" in df.columns
        else 0
    )

    return {
        "total": len(df),
        "signals": int(signal_mask.sum()),
        "high_critical": int(
            (signal_mask & severity.isin(["HIGH", "CRITICAL"])).sum()
        ),
        "open_signals": open_signals,
        "domains": domains,
        "events": int(event_mask.sum()),
    }



def latest_feed_view(feed: list[dict]) -> list[dict]:
    """Collapse historical repeats to the latest item per signal/event key.

    Risk signals are stored as an append-only history. The operational feed should
    default to the latest state for each signal type/entity rather than presenting
    every historical trigger as a separate current issue.
    """
    if not feed:
        return []

    latest: dict[tuple, dict] = {}
    for item in feed:
        item_type = str(item.get("item_type") or "")
        if item_type == "SIGNAL":
            key = (
                "SIGNAL",
                str(item.get("signal_type") or item.get("title") or ""),
                str(item.get("entity_id") or ""),
            )
        else:
            key = (
                "EVENT",
                str(item.get("title") or ""),
                str(item.get("entity_id") or ""),
            )

        old = latest.get(key)
        stamp = (str(item.get("timestamp") or ""), str(item.get("generated_at") or ""))
        old_stamp = (
            (str(old.get("timestamp") or ""), str(old.get("generated_at") or ""))
            if old else None
        )
        if old is None or stamp > old_stamp:
            latest[key] = item

    out = list(latest.values())
    out.sort(
        key=lambda x: (
            str(x.get("timestamp") or ""),
            str(x.get("generated_at") or ""),
            -SEVERITY_PRIORITY.get(str(x.get("severity") or "INFO"), 9),
        ),
        reverse=True,
    )
    return out


def signal_value_table(case) -> pd.DataFrame:
    signal = dict(case.signal)
    typ = str(signal.get("signal_type") or "")

    if typ in {"CURVE_STEEPENING", "CURVE_FLATTENING"}:
        current_unit = baseline_unit = change_unit = threshold_unit = "bp"
    elif typ == "YIELD_MOVE_HIGH":
        current_unit = baseline_unit = "%"
        change_unit = threshold_unit = "bp"
    elif typ == "OMO_RATE_CHANGE_HIGH":
        current_unit = baseline_unit = "%"
        change_unit = threshold_unit = "bp"
    elif typ == "OMO_VOLUME_CHANGE_HIGH":
        current_unit = baseline_unit = "tỷ VND"
        change_unit = threshold_unit = "%"
    elif typ.startswith("FX_"):
        current_unit = baseline_unit = change_unit = "VND/USD"
        threshold_unit = "%"
    else:
        current_unit = baseline_unit = change_unit = threshold_unit = ""

    rows = [
        ("Giá trị hiện tại", signal.get("current_value"), current_unit),
        ("Mức tham chiếu", signal.get("baseline_value"), baseline_unit),
        ("Thay đổi", signal.get("absolute_change"), change_unit),
    ]
    if signal.get("relative_change") is not None:
        rows.append(("Thay đổi tương đối", signal.get("relative_change"), "%"))
    rows.append(("Ngưỡng cảnh báo", signal.get("threshold"), threshold_unit))

    df = pd.DataFrame(rows, columns=["Chỉ tiêu", "Giá trị", "Đơn vị"])
    return df[df["Giá trị"].notna()].reset_index(drop=True)

EVIDENCE_LABELS = {
    "current_period": "Ngày dữ liệu",
    "previous_period": "Ngày tham chiếu",
    "unit": "Đơn vị",
    "curve_type": "Loại đường cong",
    "tenor": "Kỳ hạn",
    "source": "Nguồn",
    "metric_id": "Metric",
    "entity_id": "Đối tượng",
    "reason": "Lý do",
    "current_value": "Giá trị hiện tại",
    "baseline_value": "Mức tham chiếu",
    "threshold": "Ngưỡng cảnh báo",
}


def evidence_summary(case, limit: int = 12) -> pd.DataFrame:
    """Return a compact business-readable view of deterministic signal evidence."""
    evidence = case.evidence if isinstance(case.evidence, dict) else {}
    rows: list[tuple[str, Any]] = []
    for key, value in evidence.items():
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        label = EVIDENCE_LABELS.get(str(key), str(key).replace("_", " ").strip().title())
        display = value
        if isinstance(value, float):
            display = f"{value:,.4f}"
        rows.append((label, display))
        if len(rows) >= limit:
            break
    return pd.DataFrame(rows, columns=["Bằng chứng", "Giá trị"])


def case_priority(case) -> dict[str, str]:
    signal = dict(case.signal)
    severity = str(signal.get("severity") or "INFO").upper()
    dq = str(case.data_quality.get("status") or "OK").upper()

    if dq == "REVIEW":
        priority = "XÁC MINH DỮ LIỆU"
        rationale = "Bằng chứng liên quan có cờ dữ liệu cần rà soát trước khi diễn giải rủi ro."
    elif severity == "CRITICAL":
        priority = "KHẨN"
        rationale = "Signal ở mức CRITICAL và dữ liệu chưa cho thấy yêu cầu dừng diễn giải."
    elif severity == "HIGH":
        priority = "CAO"
        rationale = "Signal ở mức HIGH; cần review driver và exposure liên quan trong ngày."
    elif severity == "MEDIUM":
        priority = "THEO DÕI"
        rationale = "Signal ở mức MEDIUM; cần theo dõi xác nhận từ các quan sát tiếp theo."
    else:
        priority = "THÔNG TIN"
        rationale = "Signal chưa ở mức cần escalation tức thời."

    return {
        "priority": priority,
        "rationale": rationale,
        "severity_vi": SEVERITY_VI.get(severity, severity),
        "dq_vi": DQ_VI.get(dq, dq),
    }


def next_actions(case) -> list[str]:
    signal = dict(case.signal)
    domain = str(signal.get("domain") or "OTHER").upper()
    severity = str(signal.get("severity") or "INFO").upper()
    dq = str(case.data_quality.get("status") or "OK").upper()

    actions: list[str] = []

    if dq in {"REVIEW", "CAUTION"}:
        actions.append(
            "Xác minh nguồn, timestamp, đơn vị và quality flag trước khi kết luận từ signal."
        )

    actions.append(
        DOMAIN_ACTIONS.get(
            domain,
            "Rà soát driver, exposure liên quan và các quan sát xác nhận tiếp theo.",
        )
    )

    if severity in {"HIGH", "CRITICAL"} and dq != "REVIEW":
        actions.append(
            "Chuẩn bị escalation nếu signal được xác nhận và exposure/limit cho thấy tác động đáng kể."
        )
    elif severity == "MEDIUM":
        actions.append(
            "Tăng tần suất theo dõi và kiểm tra xem tín hiệu có lặp lại ở phiên kế tiếp hay không."
        )

    return actions


def escalation_guidance(case) -> str:
    signal = dict(case.signal)
    severity = str(signal.get("severity") or "INFO").upper()
    dq = str(case.data_quality.get("status") or "OK").upper()

    if dq == "REVIEW":
        return (
            "Chưa escalation theo tín hiệu kinh tế trước khi xác minh dữ liệu; "
            "nếu lỗi dữ liệu ảnh hưởng báo cáo/limit thì escalation theo luồng Data Quality."
        )
    if severity == "CRITICAL":
        return "Escalation ngay sau khi xác nhận dữ liệu và mức độ liên quan tới exposure/limit."
    if severity == "HIGH":
        return "Review trong ngày; escalation nếu exposure, P&L, limit hoặc stress result xác nhận mức độ trọng yếu."
    if severity == "MEDIUM":
        return "Theo dõi tăng cường; escalation nếu tín hiệu lặp lại hoặc mức sử dụng hạn mức xấu đi."
    return "Theo dõi định kỳ; chưa có trigger escalation từ severity hiện tại."


def case_workflow(case, persisted_case: dict | None = None) -> list[dict[str, str]]:
    signal = dict(case.signal)
    case_status = (
        str(persisted_case.get("status") or "OPEN").upper()
        if persisted_case
        else None
    )
    dq = str(case.data_quality.get("status") or "OK").upper()
    domain = str(signal.get("domain") or "OTHER").upper()

    return [
        {
            "step": "1. Signal",
            "state": "ĐÃ PHÁT HIỆN",
            "detail": f"{SEVERITY_VI.get(str(signal.get('severity') or 'INFO').upper(), signal.get('severity') or 'INFO')} · {DOMAIN_VI.get(domain, domain)}",
        },
        {
            "step": "2. Xác minh dữ liệu",
            "state": DQ_VI.get(dq, dq),
            "detail": str(case.data_quality.get("note") or ""),
        },
        {
            "step": "3. Driver / context",
            "state": "SẴN SÀNG RÀ SOÁT" if case.related_observations else "THIẾU CONTEXT",
            "detail": f"{len(case.related_observations)} quan sát liên quan; {case.historical_context.get('count', 0)} điểm lịch sử cho metric chính.",
        },
        {
            "step": "4. Hành động",
            "state": "CẦN RÀ SOÁT",
            "detail": DOMAIN_ACTIONS.get(
                domain,
                "Rà soát driver và exposure liên quan.",
            ),
        },
        {
            "step": "5. Trạng thái case",
            "state": STATUS_VI.get(case_status, case_status) if persisted_case else "CHƯA MỞ CASE",
            "detail": (
                "Trạng thái case được lưu và theo dõi trong hệ thống."
                if persisted_case
                else "Signal chưa được đưa vào luồng xử lý case."
            ),
        },
    ]


def compact_related_observations(case, limit: int = 12) -> pd.DataFrame:
    rows = list(case.related_observations or [])[:limit]
    if not rows:
        return pd.DataFrame()

    keep = [
        "period_end",
        "metric_id",
        "entity_id",
        "value",
        "unit",
        "source",
        "quality_flag",
        "observation_method",
    ]
    df = pd.DataFrame(rows)
    cols = [c for c in keep if c in df.columns]
    return df[cols].copy()
