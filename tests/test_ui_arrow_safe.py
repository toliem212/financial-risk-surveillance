from uuid import UUID

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


def test_uuid_only_column_is_arrow_safe():
    df = pd.DataFrame({
        "Đối tượng": [
            UUID("2a248370-c490-527a-9e6b-73aee9f6c4d7"),
            UUID("9dc82d57-c6cb-5f3f-b64f-bafbb355ead4"),
        ]
    })
    out = make_arrow_safe(df)
    assert out["Đối tượng"].map(type).eq(str).all()
    # This is the same serialization boundary Streamlit uses.
    import pyarrow as pa
    table = pa.Table.from_pandas(out, preserve_index=False)
    assert table.num_rows == 2
