import pandas as pd

from src.ui.dataframe import make_arrow_safe


def test_mixed_numeric_uuid_value_is_arrow_safe():
    df = pd.DataFrame({
        "value": [4.41, "8e00bb48-b281-5e46-8988-89edd72be29d", None],
        "metric_id": ["HNX.GOV.TENOR_YIELD", "EVENT", "OTHER"],
    })
    out = make_arrow_safe(df)
    assert str(out["value"].dtype) == "string"
    assert out.loc[0, "value"] == "4.41"
    assert out.loc[1, "value"] == "8e00bb48-b281-5e46-8988-89edd72be29d"


def test_json_like_object_is_rendered_as_text():
    df = pd.DataFrame({"payload": [{"b": 2, "a": 1}, [1, 2]]})
    out = make_arrow_safe(df)
    assert out["payload"].map(type).eq(str).all()
