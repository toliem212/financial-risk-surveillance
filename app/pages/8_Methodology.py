from pathlib import Path
import sys

# Make repository root importable on local Windows and Streamlit Cloud.
_REPO_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from __future__ import annotations

import streamlit as st

from src.ui.display import render_sidebar
from src.version import PROJECT_VERSION

st.set_page_config(page_title="Phương pháp & Giới hạn", layout="wide")
render_sidebar()
st.title("Phương pháp & Giới hạn")
st.caption(f"Vietnam Financial Risk Surveillance — {PROJECT_VERSION}")

st.markdown("""
### Phạm vi sản phẩm
Ứng dụng giám sát **dữ liệu thị trường công khai**. Hệ thống không suy đoán vị thế, hạn mức, P&L, tỷ lệ thanh khoản hay mức nắm giữ tài sản nội bộ của bất kỳ tổ chức nào.

### Ngữ nghĩa dữ liệu
- **FLOW**: đại lượng cộng dồn trong một khoảng thời gian, ví dụ khối lượng OMO trúng thầu.
- **STOCK**: quy mô tồn tại tại một thời điểm/cuối kỳ.
- **SNAPSHOT**: giá trị thị trường/tham chiếu tại một thời điểm.

Dữ liệu tuần của VIRA được tách theo từng metric. OMO flow tuần không được biến thành số liệu thứ Sáu trừ khi thỏa mãn nghiêm ngặt quy tắc **Friday residual** cho đại lượng cộng được.

### Chất lượng dữ liệu
- **A**: quan sát/sự kiện trực tiếp từ nguồn công khai có thẩm quyền.
- **B**: dữ liệu suy ra/đối chiếu có hỗ trợ mạnh.
- **C**: nguồn thứ cấp hoặc chưa đầy đủ.
- **D**: cần rà soát.
- **X**: không hợp lệ/bị loại.

### Đường cong lợi suất TPCP
Lợi suất theo kỳ hạn suy ra từ giao dịch HNX công khai được ghi rõ là **derived public-trade tenor curve**. Không trình bày chúng như bộ đường cong lợi suất thương mại/chính thức của HNX.

### Historical Replay
- **SYSTEM_KNOWN**: chống hindsight nghiêm ngặt, chỉ dùng bản ghi pipeline đã thực sự quan sát/fetch trước cutoff.
- **SOURCE_AVAILABLE**: reconstruction phục vụ nghiên cứu theo thời điểm nguồn công bố, có thể gồm dữ liệu được backfill sau đó.

### Ranh giới AI
OpenAI enrichment là tùy chọn. Dữ liệu, tính toán và cảnh báo deterministic vẫn là lõi giám sát. AI có thể giải thích signal hoặc hỗ trợ phân loại disclosure khó; AI không tạo dữ liệu thị trường còn thiếu và không tính core risk metric.

### Giới hạn đã biết
Website công khai có thể thay đổi HTML, chặn automation hoặc công bố chậm. Source run thất bại phải được coi là dữ liệu thiếu/không khả dụng, **không phải hoạt động bằng 0**. Backfill lịch sử CBIS và event-sourced outstanding chưa được coi là exhaustive trong release candidate này.
""")
