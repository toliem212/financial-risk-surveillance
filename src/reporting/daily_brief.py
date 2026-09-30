from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        x = float(value)
    except Exception:
        return str(value)
    if abs(x) >= 1000:
        return f"{x:,.{digits}f}"
    return f"{x:.{digits}f}"


def _latest_metric(observations: list[dict], metric_id: str, entity_contains: str | None = None) -> dict | None:
    candidates = [o for o in observations if str(o.get("metric_id")) == metric_id]
    if entity_contains:
        candidates = [o for o in candidates if entity_contains in str(o.get("entity_id") or "")]
    if not candidates:
        return None
    return max(candidates, key=lambda o: (str(o.get("period_end") or ""), str(o.get("fetched_at") or "")))


def _metric_line(label: str, obs: dict | None) -> str:
    if not obs:
        return f"- {label}: chưa có dữ liệu"
    return (
        f"- {label}: {_fmt_num(obs.get('value'))} {obs.get('unit') or ''} "
        f"(kỳ {obs.get('period_end')}, nguồn {obs.get('source')}, chất lượng {obs.get('quality_flag')})"
    )


def build_daily_risk_brief(store, *, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    runs = store.recent_source_runs(100)
    signals = store.recent_signals(300)
    observations = store.recent_observations(limit=5000)
    events = store.recent_bond_events(100)
    cases = store.recent_investigation_cases(200)

    signals = sorted(
        signals,
        key=lambda s: (SEVERITY_RANK.get(str(s.get("severity") or "INFO"), 0), str(s.get("generated_at") or "")),
        reverse=True,
    )
    elevated = [s for s in signals if SEVERITY_RANK.get(str(s.get("severity") or "INFO"), 0) >= 2]
    domain_counts = Counter(str(s.get("domain") or "OTHER") for s in elevated)

    signal_by_id = {str(s.get("signal_id")): s for s in signals}
    active_cases = [c for c in cases if str(c.get("status") or "OPEN").upper() != "CLOSED"]
    escalated_cases = [c for c in active_cases if str(c.get("status") or "").upper() == "ESCALATED"]

    lines: list[str] = [
        "# Bản tin Giám sát Rủi ro Tài chính Việt Nam — Daily Risk Brief",
        "",
        f"Thời điểm tạo: {generated_at.isoformat()}",
        "",
        "> Prototype giám sát từ dữ liệu công khai. Signal là cảnh báo phân tích, không phải khuyến nghị đầu tư hay kết luận về rủi ro nội bộ của một ngân hàng cụ thể.",
        "",
        "## Tóm tắt điều hành",
    ]
    if elevated:
        top = elevated[:5]
        lines.append(f"- Có {len(elevated)} deterministic signal mức MEDIUM/HIGH/CRITICAL trong lịch sử signal gần đây.")
        lines.append("- Các mục cần chú ý cao nhất:")
        for s in top:
            lines.append(
                f"  - [{s.get('severity')}] {s.get('domain')} — {s.get('signal_type')}"
                + (f" ({s.get('entity_id')})" if s.get("entity_id") else "")
            )
    else:
        lines.append("- Không có deterministic signal mức MEDIUM/HIGH/CRITICAL trong cửa sổ dữ liệu hiện tại.")
    if domain_counts:
        lines.append("- Cơ cấu signal elevated: " + ", ".join(f"{k}={v}" for k, v in domain_counts.most_common()))

    lines += ["", "## Investigation & escalation"]
    if active_cases:
        lines.append(
            f"- Có {len(active_cases)} case đang xử lý; trong đó {len(escalated_cases)} case ở trạng thái ESCALATED."
        )
        for c in active_cases[:5]:
            sig = signal_by_id.get(str(c.get("signal_id")), {})
            lines.append(
                f"- [{c.get('status')}] {c.get('priority') or '—'} · "
                f"{sig.get('domain') or 'OTHER'}"
                + (f" · {sig.get('entity_id')}" if sig.get("entity_id") else "")
                + f" · owner={c.get('owner') or 'chưa phân công'}"
            )
    else:
        lines.append("- Không có investigation case đang xử lý.")

    lines += ["", "## Thị trường tiền tệ & thanh khoản"]
    lines.append(_metric_line("Lãi suất OMO 7D của NHNN", _latest_metric(observations, "SBV.OMO.RATE", ":7D")))
    lines.append(_metric_line("Lãi suất VND O/N theo VIRA", _latest_metric(observations, "VIRA.IBOR.RATE", "VND:ON")))
    lines.append(_metric_line("Dư nợ OMO theo VIRA", _latest_metric(observations, "VIRA.OMO.REPO.OUTSTANDING")))

    lines += ["", "## Áp lực tỷ giá (FX Pressure)"]
    lines.append(_metric_line("USD/VND liên ngân hàng", _latest_metric(observations, "VIRA.FX.INTERBANK")))
    lines.append(_metric_line("Mức bán tham chiếu của NHNN", _latest_metric(observations, "VIRA.FX.SBV_SELL")))
    fx_signals = [s for s in signals if str(s.get("domain")) == "FX"][:3]
    for s in fx_signals:
        lines.append(f"- Signal [{s.get('severity')}]: {s.get('signal_type')}")

    lines += ["", "## TPCP / Lãi suất"]
    for tenor in ("2Y", "5Y", "10Y", "15Y"):
        lines.append(_metric_line(f"Lợi suất {tenor} suy ra từ giao dịch công khai", _latest_metric(observations, "HNX.GOV.TENOR_YIELD", tenor)))
    rate_signals = [s for s in signals if str(s.get("domain")) == "RATES"][:3]
    for s in rate_signals:
        lines.append(f"- Signal [{s.get('severity')}]: {s.get('signal_type')} ({s.get('entity_id') or 'market'})")

    lines += ["", "## Radar sự kiện Trái phiếu Doanh nghiệp"]
    if events:
        for e in events[:5]:
            lines.append(
                f"- {e.get('event_date') or e.get('effective_date') or '—'} — {e.get('event_type')} — "
                f"{e.get('bond_id') or e.get('issuer_id') or 'chưa liên kết'} (quality {e.get('quality_flag')})"
            )
    else:
        lines.append("- Chưa có sự kiện TPDN trong cửa sổ dữ liệu hiện tại.")

    lines += ["", "## Bối cảnh vĩ mô cấu trúc (Structural Macro Context)"]
    macro_specs = [
        ("Tổng M2 (M2 total)", "SBV.MACRO.M2.LEVEL", "TONG_PHUONG_TIEN_THANH_TOAN"),
        ("Tăng trưởng M2 từ đầu năm", "SBV.MACRO.M2.GROWTH_YTD", "TONG_PHUONG_TIEN_THANH_TOAN"),
        ("Tổng tín dụng", "SBV.MACRO.CREDIT.LEVEL", "TONG_CONG"),
        ("Tăng trưởng tín dụng từ đầu năm", "SBV.MACRO.CREDIT.GROWTH_YTD", "TONG_CONG"),
        ("LDR toàn hệ thống", "SBV.MACRO.LDR.LEVEL", "TOAN_HE_THONG"),
    ]
    any_macro = False
    for label, metric, entity in macro_specs:
        obs = _latest_metric(observations, metric, entity)
        if obs:
            any_macro = True
        lines.append(_metric_line(label, obs))
    if not any_macro:
        lines.append("- Macro context là lớp tùy chọn và chưa được ingest.")

    lines += ["", "## Sức khỏe dữ liệu & nguồn"]
    if runs:
        latest_by_worker: dict[str, dict] = {}
        for r in runs:
            worker = str(r.get("worker") or r.get("source") or "unknown")
            old = latest_by_worker.get(worker)
            if old is None or str(r.get("started_at") or "") > str(old.get("started_at") or ""):
                latest_by_worker[worker] = r
        for worker, r in sorted(latest_by_worker.items()):
            lines.append(
                f"- {worker}: {r.get('status')} · lần chạy gần nhất {r.get('started_at')}"
                + (f" · {r.get('error_type')}: {r.get('error_message')}" if r.get("error_type") else "")
            )
    else:
        lines.append("- Chưa có source-run history.")

    dq = [s for s in signals if str(s.get("domain")) == "DATA_QUALITY"][:5]
    if dq:
        lines += ["", "## Ngoại lệ chất lượng dữ liệu"]
        for s in dq:
            evidence = _json(s.get("evidence_json"))
            lines.append(
                f"- [{s.get('severity')}] {s.get('signal_type')} — {s.get('entity_id') or ''}"
                + (f" — {evidence.get('reason')}" if evidence.get("reason") else "")
            )

    lines += [
        "",
        "## Cần theo dõi tiếp (What To Monitor Next)",
        "- Kết quả OMO tiếp theo và cấu trúc kỳ hạn thị trường tiền tệ.",
        "- USD/VND liên ngân hàng và khoảng cách tới các mức tham chiếu điều hành.",
        "- Độ rộng biến động đường cong TPCP và thanh khoản thứ cấp.",
        "- Disclosure HNX CBIS tiếp theo đối với issuer/bond có sự kiện đáng chú ý.",
        "- Mismatch nguồn, thay đổi schema/parser hoặc stale-source trước khi diễn giải chỉ tiêu bị ảnh hưởng.",
        "",
        "## Ghi chú phương pháp",
        "Bản tin được tạo deterministic từ observation, event và rule-based signal đã lưu. Hệ thống không suy đoán vị thế, hạn mức, P&L hay direct exposure nội bộ của ngân hàng. Chỉ báo vĩ mô là bối cảnh chậm và không được coi là intraday risk alert.",
    ]
    return "\n".join(lines) + "\n"
