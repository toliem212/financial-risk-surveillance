from __future__ import annotations

import json
from typing import Any

import pandas as pd


def _display_scalar(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(value)
    return value


def make_arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize mixed object columns before Streamlit/PyArrow serialization.

    Mixed columns such as timeline `value` can legally contain both numbers and UUIDs.
    PyArrow may infer the column as numeric and fail on later text. For mixed text/non-
    text object columns, render the entire column as pandas StringDtype. JSON-like
    values are rendered deterministically as text.
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        if out[col].dtype != object:
            continue
        out[col] = out[col].map(_display_scalar)
        non_null = out[col].dropna()
        if non_null.empty:
            continue
        has_text = non_null.map(lambda x: isinstance(x, str)).any()
        has_non_text = non_null.map(lambda x: not isinstance(x, str)).any()
        if has_text and has_non_text:
            out[col] = out[col].astype("string")
    return out
