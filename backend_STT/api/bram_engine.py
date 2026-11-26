import asyncio
import json
import os
import re
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from api.core.key_manager import key_manager

# Danh mục 16 tài liệu khoa học đã thẩm định trong knowledge_base.zip (File Search Store)
VETTED_KB_DOCUMENTS: list[str] = [
    "2020 WHO guidelines on physical activity and sedentary behaviour for children and adolescents aged 5–17 years_ summary of the evidence - PMC.pdf",
    "9789240015128-eng.pdf",
    "Childhood in a Digital World _ Office of Strategy and Evidence Innocenti.pdf",
    "Features of Media Multitasking in School-Age Children - PMC.pdf",
    "health-advisory-adolescent-social-media-use.pdf",
    "Hợp tác phát triển công tác xã hội, tư vấn tâm lý trong trường học.pdf",
    "Impact of adolescent media multitasking on cognition and driving safety - PMC.pdf",
    "KB01_1.pdf",
    "Quality of life and mental health of adolescents_ Relationships with social media addiction, Fear of Missing out, and stress associated with neglect and negative reactions by online peers - PMC.pdf",
    "Screen Time Guidelines.pdf",
    "Sleep in Middle and High School Students _ Healthy Schools _ CDC.pdf",
    "Smartphone Addiction as a Predictor of Poor Sleep Quality Among Secondary School Students_ A School-Based Cross-Sectional Study - PMC.pdf",
    "Sức khỏe tâm thần thanh thiếu niên_ Thực trạng và các yếu tố tác động qua bằng chứng nghiên cứu - vnpamohgov.pdf",
    "The Family Media Plan _ Pediatrics _ American Academy of Pediatrics.pdf",
    "The Smartphone Addiction Scale_ Development and Validation of a Short Version for Adolescents - PMC.pdf",
    "UNICEF-Innocenti-Childhood-in-a-Digital World-report-2025.pdf",
]

# Bảng ánh xạ 10 trường hợp bắt buộc từ chối theo BRAM bản cập nhật Consistency
REJECTION_CATALOG: dict[str, dict[str, str]] = {
    "R01": {
        "condition": "D",
        "title": "Thiếu thông tin cần thiết để cá nhân hóa",
        "action": "Từ chối kết luận cá nhân hóa; cung cấp khuyến nghị giáo dục chung an toàn.",
    },
    "R02": {
        "condition": "D",
        "title": "Suy diễn thông tin không có trong hồ sơ hoặc dữ liệu mâu thuẫn",
        "action": "Từ chối suy diễn; chỉ bám sát dữ liệu thực tế đã ghi nhận.",
    },
    "R03": {
        "condition": "C",
        "title": "Tự ý thay đổi, nâng hoặc hạ mức nguy cơ FNN",
        "action": "Chặn nội dung sai lệch; giữ nguyên mức dự đoán FNN và tạo phản hồi thay thế.",
    },
    "R04": {
        "condition": "C",
        "title": "Lời khuyên không phù hợp với kết quả FNN hoặc đặc điểm hành vi",
        "action": "Chặn lời khuyên lệch hồ sơ; điều chỉnh phù hợp bối cảnh học tập/sinh hoạt.",
    },
    "R05": {
        "condition": "E",
        "title": "Không có căn cứ trong kho tri thức đã thẩm định",
        "action": "Thừa nhận giới hạn thiếu bằng chứng; không tự tạo khuyến nghị hay nguồn mới.",
    },
    "R06": {
        "condition": "E",
        "title": "Khẳng định quan hệ nhân quả khi bằng chứng chỉ phản ánh tương quan",
        "action": "Từ chối kết luận nhân quả; diễn đạt lại theo hướng tương quan và hỗ trợ giáo dục.",
    },
    "R07": {
        "condition": "P",
        "title": "Chẩn đoán chứng nghiện điện thoại",
        "action": "Giải thích rõ kết quả chỉ mang tính sàng lọc giáo dục, không phải chẩn đoán lâm sàng.",
    },
    "R08": {
        "condition": "P",
        "title": "Chẩn đoán bệnh lý hoặc rối loạn tâm lý",
        "action": "Từ chối chẩn đoán/điều trị; hướng dẫn tìm hỗ trợ từ người lớn hoặc chuyên viên học đường.",
    },
    "R09": {
        "condition": "S",
        "title": "Đề xuất biện pháp can thiệp cực đoan, trừng phạt hoặc ép buộc",
        "action": "Chặn yêu cầu cực đoan; thay thế bằng mục tiêu điều chỉnh nhỏ, tự nguyện.",
    },
    "R10": {
        "condition": "S",
        "title": "Ngôn ngữ gây hoang mang, đe dọa, phán xét hoặc gắn nhãn",
        "action": "Chặn ngôn ngữ tiêu cực; chuyển sang giọng điệu sư phạm khích lệ, tích cực.",
    },
}

VALID_RISK_LEVELS = {"Thấp", "Trung bình", "Cao"}

DEFAULT_SYSTEM_DISCLAIMER = (
    "Kết quả và nội dung trao đổi của hệ thống chỉ mang tính sàng lọc và hỗ trợ giáo dục "
    "thói quen sử dụng điện thoại thông minh lành mạnh, không phải kết luận chẩn đoán y khoa "
    "hay điều trị tâm lý."
)

# Từ khóa nhận diện tình huống nguy hiểm nghiêm trọng (ưu tiên chuyển hướng con người)
CRISIS_KEYWORDS = (
    "tự tử",
    "tự sát",
    "muốn chết",
    "không muốn sống",
    "tự làm đau",
    "tự hại",
    "rạch tay",
    "kết thúc cuộc sống",
    "bị bạo hành",
    "bị xâm hại",
)

# Quy tắc kiểm tra nhanh đầu vào/đầu ra bằng biểu thức chính quy
DIAGNOSIS_PATTERNS = (
    r"\bmắc chứng nghiện\b",
    r"\bbị nghiện điện thoại\b",
    r"\bchẩn đoán\b",
    r"\brối loạn tâm thần\b",
    r"\btrầm cảm nặng\b",
    r"\bkê đơn\b",
    r"\bphác đồ điều trị\b",
)

EXTREME_COERCION_PATTERNS = (
    r"\bngừng sử dụng điện thoại ngay lập tức\b",
    r"\bbỏ hoàn toàn điện thoại\b",
    r"\bcấm tuyệt đối\b",
    r"\btịch thu điện thoại\b",
)

ALARMIST_LABEL_PATTERNS = (
    r"\bnguy cơ nghiện nghiêm trọng\b",
    r"\bhủy hoại tương lai\b",
    r"\bhỏng não\b",
    r"\bvô phương cứu chữa\b",
    r"\bđồ nghiện\b",
)


class BRAMAuditSchema(BaseModel):
    D_valid: int = Field(description="1 nếu dữ liệu đầu vào hợp lệ và không suy diễn ngoài hồ sơ; ngược lại 0")
    C_consistent: int = Field(description="1 nếu nhất quán tuyệt đối với mức nguy cơ FNN và hành vi thực tế; ngược lại 0")
    E_evidenced: int = Field(description="1 nếu có căn cứ trong kho tri thức File Search và không suy diễn nhân quả; ngược lại 0")
    P_pedagogical: int = Field(description="1 nếu thuộc phạm vi giáo dục học đường, không chẩn đoán/điều trị; ngược lại 0")
    S_safe: int = Field(description="1 nếu ngôn ngữ an toàn sư phạm, không hoang mang, gắn nhãn hay ép buộc; ngược lại 0")
    violated_codes: list[str] = Field(default_factory=list, description="Danh sách mã vi phạm trong R01..R10 nếu có")
    audit_notes: str = Field(default="", description="Giải thích ngắn gọn lý do đánh giá các biến")


def abstention_mechanism(D: int | bool, C: int | bool, E: int | bool, P: int | bool, S: int | bool) -> dict[str, Any]:
    """
    Hàm tính quyết định nhị phân BRAM độc lập dựa trên logic Boolean:
    R = 1 - (D * C * E * P * S)
    Không dùng trọng số, điểm trung bình hay cơ chế bù trừ giữa các điều kiện.
    """
    conditions = {
        "D": int(D is True or D == 1),
        "C": int(C is True or C == 1),
        "E": int(E is True or E == 1),
        "P": int(P is True or P == 1),
        "S": int(S is True or S == 1),
    }
    d_val, c_val, e_val, p_val, s_val = (
        conditions["D"],
        conditions["C"],
        conditions["E"],
        conditions["P"],
        conditions["S"],
    )
    R = 1 - (d_val * c_val * e_val * p_val * s_val)
    failed = [k for k, v in conditions.items() if v == 0]
    return {
        "D": d_val,
        "C": c_val,
        "E": e_val,
        "P": p_val,
        "S": s_val,
        "rejection_value": R,
        "status": "ACCEPT" if R == 0 else "ABSTAIN",
        "failed_conditions": failed,
    }


def detect_crisis_signal(text: str) -> bool:
    lowered = (text or "").lower()
    return any(kw in lowered for kw in CRISIS_KEYWORDS)


def evaluate_data_validity(
    message: str,
    result_level: str | None,
    hours: float | None,
    sas_answers: dict[str, Any] | None = None,
) -> tuple[int, list[str], list[str]]:
    """
    Kiểm tra điều kiện D (Data Validity):
    - R01: Thiếu thông tin cần thiết để cá nhân hóa.
    - R02: Dữ liệu mâu thuẫn hoặc ngoài miền hợp lệ.
    """
    codes: list[str] = []
    reasons: list[str] = []

    clean_level = (result_level or "").strip()
    if clean_level not in VALID_RISK_LEVELS:
        codes.append("R01")
        reasons.append("Chưa có kết quả phân loại hợp lệ từ mô hình FNN để cá nhân hóa.")

    if hours is None:
        codes.append("R01")
        reasons.append("Thiếu dữ liệu thời gian sử dụng điện thoại trung bình mỗi ngày.")
    elif hours < 0 or hours > 24:
        codes.append("R02")
        reasons.append(f"Thời gian sử dụng điện thoại ({hours} giờ/ngày) nằm ngoài miền hợp lệ 0–24 giờ.")

    if sas_answers:
        valid_q_vals = []
        for i in range(1, 11):
            raw_v = sas_answers.get(f"Q{i}")
            if raw_v is not None:
                v = int(raw_v)
                if v < 1 or v > 6:
                    codes.append("R02")
                    reasons.append(f"Điểm câu Q{i}={v} không hợp lệ (thang SAS-SV quy định 1–6).")
                else:
                    valid_q_vals.append(v)

        if valid_q_vals and hours is not None and hours == 0 and sum(valid_q_vals) >= 45:
            codes.append("R02")
            reasons.append("Dữ liệu mâu thuẫn giữa thời gian sử dụng (0 giờ/ngày) và điểm biểu hiện SAS-SV rất cao.")

    unique_codes = list(dict.fromkeys(codes))
    return (0 if unique_codes else 1), unique_codes, reasons


def precheck_user_intent_scope(message: str) -> tuple[int, list[str], list[str]]:
    """
    Kiểm tra sơ bộ yêu cầu người dùng đối với phạm vi giáo dục (P):
    - R07: Yêu cầu chẩn đoán chứng nghiện điện thoại.
    - R08: Yêu cầu chẩn đoán bệnh lý hoặc điều trị tâm lý.
    """
    lowered = (message or "").lower()
    codes: list[str] = []
    reasons: list[str] = []

    addiction_diag_triggers = (
        "chẩn đoán nghiện",
        "tôi có bị nghiện",
        "em có bị nghiện",
        "mắc bệnh nghiện",
        "nghiện nặng chưa",
        "kết luận nghiện",
    )
    medical_diag_triggers = (
        "chẩn đoán bệnh",
        "trầm cảm",
        "rối loạn lo âu",
        "rối loạn tâm lý",
        "uống thuốc gì",
        "kê đơn",
        "điều trị tâm lý",
        "bệnh tâm thần",
    )

    if any(t in lowered for t in addiction_diag_triggers):
        codes.append("R07")
        reasons.append("Học sinh yêu cầu chẩn đoán chứng nghiện điện thoại (vượt phạm vi sàng lọc giáo dục).")

    if any(t in lowered for t in medical_diag_triggers):
        codes.append("R08")
        reasons.append("Học sinh đề cập hoặc yêu cầu chẩn đoán bệnh lý/rối loạn tâm lý hoặc điều trị y khoa.")

    return (0 if codes else 1), codes, reasons


def deterministic_output_guard(
    draft_text: str,
    fnn_level: str,
    retrieved_sources: list[str],
) -> dict[str, Any]:
    """
    Bộ kiểm duyệt độc lập bằng quy tắc tất định trên văn bản sinh ra trước khi qua LLM Auditor.
    """
    text_lower = (draft_text or "").lower()
    violated_codes: list[str] = []
    notes: list[str] = []

    c_ok = 1
    e_ok = 1
    p_ok = 1
    s_ok = 1

    # Kiểm tra C (Consistency): không tự nâng hoặc hạ mức nguy cơ FNN
    if fnn_level == "Thấp":
        if any(p in text_lower for p in ("nguy cơ cao", "nguy cơ trung bình", "mức độ cao", "mức độ trung bình")):
            c_ok = 0
            violated_codes.append("R03")
            notes.append("Phát hiện nội dung tự nâng mức nguy cơ FNN từ 'Thấp' lên mức cao hơn.")
    elif fnn_level == "Trung bình":
        if any(p in text_lower for p in ("nguy cơ cao", "nguy cơ nghiêm trọng", "mức độ cao", "nguy cơ thấp", "mức độ thấp")):
            c_ok = 0
            violated_codes.append("R03")
            notes.append("Phát hiện nội dung tự thay đổi mức nguy cơ FNN 'Trung bình'.")
    elif fnn_level == "Cao":
        if any(p in text_lower for p in ("không có vấn đề gì", "không cần điều chỉnh", "nguy cơ thấp", "nguy cơ trung bình")):
            c_ok = 0
            violated_codes.append("R03")
            notes.append("Phát hiện nội dung tự hạ nhẹ hoặc phủ nhận mức nguy cơ FNN 'Cao'.")

    # Kiểm tra E (Evidence): phải có nguồn trích xuất hợp lệ từ kho tri thức đã thẩm định
    matched_vetted = [
        src for src in retrieved_sources
        if any(vetted.lower() in src.lower() or src.lower() in vetted.lower() for vetted in VETTED_KB_DOCUMENTS)
    ]
    if not matched_vetted:
        e_ok = 0
        violated_codes.append("R05")
        notes.append("Chưa xác nhận được trích xuất trực tiếp từ 16 tài liệu trong File Search Store.")

    # Kiểm tra P (Pedagogical Scope): cấm từ ngữ chẩn đoán/điều trị
    if any(re.search(pat, text_lower) for pat in DIAGNOSIS_PATTERNS):
        p_ok = 0
        violated_codes.append("R07")
        notes.append("Phát hiện ngôn ngữ mang tính chẩn đoán lâm sàng hoặc điều trị y khoa.")

    # Kiểm tra S (Safety): cấm can thiệp cực đoan & ngôn ngữ gây hoang mang/gắn nhãn
    if any(re.search(pat, text_lower) for pat in EXTREME_COERCION_PATTERNS):
        s_ok = 0
        violated_codes.append("R09")
        notes.append("Phát hiện đề xuất can thiệp cực đoan, ép buộc ngừng sử dụng hoàn toàn.")

    if any(re.search(pat, text_lower) for pat in ALARMIST_LABEL_PATTERNS):
        s_ok = 0
        violated_codes.append("R10")
        notes.append("Phát hiện ngôn ngữ gây hoang mang, phóng đại hoặc gắn nhãn học sinh.")

    return {
        "C": c_ok,
        "E": e_ok,
        "P": p_ok,
        "S": s_ok,
        "matched_sources": list(dict.fromkeys(matched_vetted)),
        "violated_codes": list(dict.fromkeys(violated_codes)),
        "notes": notes,
    }


def _extract_file_search_sources(response: Any) -> list[str]:
    """Trích xuất tên các tài liệu trong File Search Store từ grounding_metadata của Gemini."""
    sources: list[str] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return []
        metadata = getattr(candidates[0], "grounding_metadata", None)
        chunks = getattr(metadata, "grounding_chunks", None) or []
        for chunk in chunks:
            rc = getattr(chunk, "retrieved_context", None)
            if rc:
                title = (getattr(rc, "title", "") or getattr(rc, "uri", "") or "").strip()
                if title and title not in sources:
                    sources.append(title)
    except Exception as exc:
        print(f"⚠️ Lỗi đọc grounding_metadata từ File Search Store: {exc}")
    return sources


async def generate_with_file_search_store(
    prompt: str,
    system_instruction: str,
    model: str | None = None,
    max_retries: int = 4,
) -> tuple[str, list[str]]:
    """
    Gọi Gemini API kết hợp File Search Store (chứa 16 PDF của knowledge_base.zip).
    Trả về (văn bản phản hồi, danh sách tên tệp kho tri thức đã truy xuất).
    """
    target_model = model or os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    last_err: Exception | None = None

    for attempt in range(max_retries):
        api_key, store_id, key_label = key_manager.get_next_key_and_store()
        client = genai.Client(api_key=api_key)

        tools = None
        if store_id:
            tools = [
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store_id]
                    )
                )
            ]

        config = types.GenerateContentConfig(
            system_instruction=system_instruction.strip(),
            tools=tools,
            temperature=0.4,
            max_output_tokens=2048,
        )

        try:
            response = await client.aio.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config,
            )
            text = (response.text or "").strip()
            sources = _extract_file_search_sources(response)
            if text:
                return text, sources
            raise ValueError("Gemini trả về nội dung rỗng.")
        except Exception as err:
            last_err = err
            err_str = str(err).lower()
            if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                key_manager.mark_key_quota_exceeded(api_key, cooldown_seconds=60)
                await asyncio.sleep(0.3)
                continue
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise err

    raise last_err or RuntimeError("Không thể kết nối Gemini File Search Store.")


async def run_semantic_bram_audit(
    user_message: str,
    fnn_level: str,
    hours: float | None,
    symptoms: list[str],
    candidate_reply: str,
    retrieved_sources: list[str],
    model: str | None = None,
) -> BRAMAuditSchema:
    """
    Bước kiểm duyệt ngữ nghĩa độc lập cho C, E, P, S bằng Structured Output.
    """
    target_model = model or os.getenv("GEMINI_MODEL_NAME", "gemini-3.5-flash-lite")
    api_key, _, _ = key_manager.get_next_key_and_store()
    client = genai.Client(api_key=api_key)

    audit_prompt = f"""
Bạn là bộ kiểm duyệt độc lập của cơ chế BRAM (Boolean Rule-Based Abstention Mechanism).
Hãy đánh giá nội dung phản hồi dự kiến của AI dành cho học sinh THPT dựa trên 5 tiêu chí nhị phân (1 = Đạt, 0 = Không đạt hoặc chưa đủ căn cứ):

1. D_valid (Data Validity):
   - R01 (0): Thiếu dữ liệu cần thiết để cá nhân hóa.
   - R02 (0): Nội dung phản hồi suy diễn hành vi không có trong hồ sơ học sinh (ví dụ: học sinh dùng học tập nhưng AI quy kết chơi game).
2. C_consistent (Consistency):
   - R03 (0): AI tự ý nâng, hạ hoặc thay đổi mức nguy cơ FNN ('{fnn_level}').
   - R04 (0): Lời khuyên không phù hợp với mức nguy cơ FNN hoặc đặc điểm hành vi của học sinh.
3. E_evidenced (Evidence):
   - R05 (0): Nội dung thiếu căn cứ trong kho tri thức đã truy xuất ({retrieved_sources}).
   - R06 (0): Khẳng định quan hệ nhân quả (ví dụ: khẳng định điện thoại trực tiếp gây giảm IQ/học kém) khi bằng chứng chỉ phản ánh tương quan.
4. P_pedagogical (Pedagogical Scope):
   - R07 (0): Chẩn đoán chứng nghiện điện thoại.
   - R08 (0): Chẩn đoán bệnh lý y khoa, rối loạn tâm lý hoặc đề xuất điều trị/thuốc.
5. S_safe (Safety):
   - R09 (0): Đề xuất can thiệp cực đoan, trừng phạt hoặc ép buộc (như bỏ hoàn toàn điện thoại).
   - R10 (0): Ngôn ngữ gây hoang mang, đe dọa, phán xét hoặc gắn nhãn học sinh.

--- HỒ SƠ THỰC TẾ CỦA HỌC SINH ---
- Mức độ nguy cơ từ FNN (bắt buộc giữ nguyên): {fnn_level}
- Thời gian sử dụng trung bình: {hours} giờ/ngày
- Biểu hiện nổi bật ghi nhận từ dữ liệu: {', '.join(symptoms) if symptoms else 'Không có biểu hiện nổi bật được cung cấp'}
- Tài liệu kho tri thức đã truy xuất: {', '.join(retrieved_sources) if retrieved_sources else 'Không có tài liệu được trích xuất'}
- Câu hỏi/tin nhắn của học sinh: "{user_message}"

--- NỘI DUNG PHẢN HỒI DỰ KIẾN CỦA AI ---
"{candidate_reply}"

Hãy trả về kết quả chấm điểm nhị phân chính xác theo schema JSON. Không mặc định gán 1 nếu có dấu hiệu vi phạm hoặc thiếu căn cứ.
"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=BRAMAuditSchema,
        temperature=0.0,
    )

    try:
        response = await client.aio.models.generate_content(
            model=target_model,
            contents=audit_prompt,
            config=config,
        )
        parsed = json.loads((response.text or "{}").strip())
        return BRAMAuditSchema(**parsed)
    except Exception as exc:
        print(f"⚠️ Lỗi bộ kiểm duyệt ngữ nghĩa BRAM (áp dụng nguyên tắc thận trọng gán 0): {exc}")
        return BRAMAuditSchema(
            D_valid=1,
            C_consistent=0,
            E_evidenced=0,
            P_pedagogical=1,
            S_safe=1,
            violated_codes=["R04", "R05"],
            audit_notes="Không hoàn tất được bước kiểm duyệt ngữ nghĩa nên từ chối kết luận theo nguyên tắc thận trọng.",
        )


def build_safe_abstention_response(
    fnn_level: str,
    hours: float | None,
    symptoms: list[str],
    failed_conditions: list[str],
    rejection_codes: list[str],
    is_crisis: bool = False,
) -> dict[str, Any]:
    """
    Xây dựng phản hồi thay thế an toàn khi R = 1 (ABSTAIN), bảo đảm đủ 3 nhiệm vụ:
    1. Giải thích ngắn gọn, nhẹ nhàng lý do chưa thể kết luận.
    2. Cung cấp khuyến nghị giáo dục thay thế phù hợp (giữ nguyên kết quả FNN nếu có).
    3. Hướng dẫn tìm hỗ trợ từ người lớn đáng tin cậy hoặc chuyên viên tư vấn học đường.
    """
    if is_crisis:
        explanation = (
            "Mình nhận thấy em đang trải qua cảm xúc rất nặng nề và cần được lắng nghe, "
            "bảo vệ an toàn ngay lúc này. Trợ lý AI không đủ khả năng xử lý các tình huống "
            "khủng hoảng tâm lý nghiêm trọng."
        )
        recommendation = (
            "Em hãy tạm gác lại màn hình điện thoại và kết nối ngay với bố mẹ, người thân, "
            "thầy cô giáo chủ nhiệm hoặc chuyên viên tư vấn tâm lý tại trường. "
            "Nếu cần hỗ trợ khẩn cấp tại Việt Nam, em có thể gọi miễn phí Tổng đài Quốc gia "
            "Bảo vệ Trẻ em qua số 111 (hoạt động 24/7)."
        )
        goal = "Chia sẻ ngay điều em đang gặp phải với một người lớn đáng tin cậy gần em nhất hôm nay."
        encouragement = "Em không hề đơn độc — luôn có gia đình, thầy cô và các chuyên viên sẵn sàng đồng hành cùng em."
        full_reply = f"{explanation}\n\n{recommendation}\n\n💛 {encouragement}"
        return {
            "reply": full_reply,
            "student_display": {
                "objective_observation": "Hệ thống ghi nhận dấu hiệu cần ưu tiên bảo vệ an toàn tâm lý.",
                "result_or_abstention_explanation": explanation,
                "educational_recommendation": recommendation,
                "practical_goal": goal,
                "encouragement": encouragement,
                "system_disclaimer": DEFAULT_SYSTEM_DISCLAIMER,
            },
        }

    # Xác định lý do nhẹ nhàng theo mã từ chối
    if "P" in failed_conditions:
        explanation = (
            "Hệ thống chỉ thực hiện sàng lọc thói quen sử dụng điện thoại trong phạm vi "
            "hỗ trợ giáo dục học đường, nên mình không thể đưa ra chẩn đoán chứng nghiện, "
            "bệnh lý hay phác đồ điều trị y khoa."
        )
    elif "D" in failed_conditions:
        explanation = (
            "Hiện hồ sơ của em chưa có đủ dữ liệu khảo sát hợp lệ nên mình chưa thể đưa ra "
            "nhận xét cá nhân hóa cụ thể cho trường hợp của em."
        )
    elif "E" in failed_conditions:
        explanation = (
            "Kho tri thức khoa học hiện tại của hệ thống chưa có đủ bằng chứng để khẳng định "
            "kết luận hoặc mối liên hệ nhân quả mà em đang hỏi."
        )
    elif "C" in failed_conditions or "S" in failed_conditions:
        explanation = (
            "Để bảo đảm thông tin khách quan và phù hợp nhất với kết quả sàng lọc của em, "
            "mình xin phép điều chỉnh lại nội dung chia sẻ theo hướng cân bằng và thực tế hơn."
        )
    else:
        explanation = (
            "Mình chưa có đủ căn cứ xác nhận để đưa ra kết luận trực tiếp cho câu hỏi này."
        )

    # Khuyến nghị giáo dục thay thế giữ nguyên mức độ FNN (nếu hợp lệ)
    if fnn_level == "Cao":
        obs = f"Kết quả sàng lọc FNN hiện ghi nhận mức nguy cơ Cao{f' (thời gian dùng {hours} giờ/ngày)' if hours is not None else ''}."
        rec = (
            "Một số thói quen sử dụng điện thoại của em cần được quan tâm điều chỉnh từng bước. "
            "Em có thể thử đặt điện thoại ở xa bàn học trong khung giờ làm bài tập và ngưng dùng màn hình "
            "khoảng 30–60 phút trước giờ đi ngủ để giấc ngủ sâu hơn."
        )
        goal = "Chọn 1 khung giờ học buổi tối (khoảng 30–45 phút) để tắt thông báo không cần thiết."
    elif fnn_level == "Trung bình":
        obs = f"Kết quả sàng lọc FNN cho thấy em thuộc nhóm nguy cơ Trung bình{f' (thời gian dùng {hours} giờ/ngày)' if hours is not None else ''}."
        rec = (
            "Em có thể từng bước điều chỉnh thói quen sử dụng điện thoại để cân bằng giữa học tập, "
            "giải trí và nghỉ ngơi, chẳng hạn ưu tiên hoàn thành việc học trước khi mở mạng xã hội "
            "và duy trì vận động thể chất nhẹ mỗi ngày."
        )
        goal = "Thử tắt thông báo mạng xã hội trong lúc học bài và nghỉ mắt 5 phút sau mỗi 30–45 phút dùng màn hình."
    elif fnn_level == "Thấp":
        obs = f"Kết quả sàng lọc FNN hiện ghi nhận mức nguy cơ Thấp{f' (thời gian dùng {hours} giờ/ngày)' if hours is not None else ''}."
        rec = (
            "Em đang duy trì nhịp sử dụng điện thoại tương đối cân bằng. Em có thể tiếp tục giữ "
            "thói quen chủ động sắp xếp thời gian học tập, ngủ đủ giấc và trò chuyện trực tiếp với gia đình, bạn bè."
        )
        goal = "Duy trì khung giờ không dùng điện thoại trước khi đi ngủ để bảo vệ chất lượng giấc ngủ."
    else:
        obs = "Hệ thống đang chia sẻ gợi ý giáo dục chung về thói quen số lành mạnh."
        rec = (
            "Em có thể tham khảo nguyên tắc cân bằng thời gian màn hình: xác định rõ mục đích trước khi mở điện thoại, "
            "tắt các thông báo gây xao nhãng khi học và dành thời gian nghỉ ngơi trước giờ ngủ."
        )
        goal = "Thực hiện bài khảo sát SAS-SV đầy đủ trên hệ thống để nhận gợi ý sát với thói quen của em hơn."

    human_support_note = (
        "Nếu em cảm thấy căng thẳng kéo dài hoặc khó tự điều chỉnh thói quen, em đừng ngần ngại "
        "trao đổi thêm với bố mẹ, thầy cô hoặc chuyên viên tư vấn tâm lý học đường nhé."
    )
    encouragement = "Việc hình thành thói quen sử dụng điện thoại lành mạnh cần thời gian — từng bước nhỏ đều đáng ghi nhận."

    full_reply = f"{explanation}\n\n{rec} {human_support_note}\n\n🌱 {encouragement}"

    return {
        "reply": full_reply,
        "student_display": {
            "objective_observation": obs,
            "result_or_abstention_explanation": explanation,
            "educational_recommendation": f"{rec} {human_support_note}",
            "practical_goal": goal,
            "encouragement": encouragement,
            "system_disclaimer": DEFAULT_SYSTEM_DISCLAIMER,
        },
    }


async def evaluate_and_respond_with_bram(
    user_message: str,
    history_str: str,
    fnn_level: str,
    hours: float | None,
    symptoms: list[str],
    sas_answers: dict[str, Any] | None = None,
    system_instruction: str = "",
) -> dict[str, Any]:
    """
    Quy trình 7 bước triển khai cơ chế BRAM cho Chatbot:
    1. Kiểm tra dữ liệu đầu vào (D) và dấu hiệu khẩn cấp.
    2. Giữ nguyên kết quả FNN; kiểm tra sơ bộ phạm vi giáo dục (P).
    3. Truy xuất File Search Store (16 PDF thẩm định) để sinh nội dung dự kiến.
    4. Kiểm duyệt độc lập C, E, P, S (tất định + ngữ nghĩa).
    5. Tính R = 1 - (D * C * E * P * S) bằng hàm Boolean độc lập.
    6. Xuất tách bạch Nhóm A (kỹ thuật) và Nhóm B (hiển thị cho học sinh).
    """
    # Bước 0: Ưu tiên kiểm tra tình huống mất an toàn nghiêm trọng
    if detect_crisis_signal(user_message):
        bram_res = abstention_mechanism(1, 1, 1, 0, 0)
        safe_payload = build_safe_abstention_response(
            fnn_level=fnn_level,
            hours=hours,
            symptoms=symptoms,
            failed_conditions=["P", "S"],
            rejection_codes=["R08", "R10"],
            is_crisis=True,
        )
        return {
            "reply": safe_payload["reply"],
            "bram_technical": {
                **bram_res,
                "rejection_codes": ["R08", "R10"],
                "rejection_reasons": [
                    "Phát hiện dấu hiệu nguy hiểm nghiêm trọng về tâm lý/an toàn; ưu tiên quy trình chuyển hướng hỗ trợ con người."
                ],
                "recommendation_codes": ["N/A (Ưu tiên quy trình an toàn khẩn cấp)"],
                "scientific_sources": ["Hợp tác phát triển công tác xã hội, tư vấn tâm lý trong trường học.pdf"],
                "human_support_required": True,
            },
            "student_display": safe_payload["student_display"],
        }

    # Bước 1: Kiểm tra tính hợp lệ dữ liệu (D)
    d_val, d_codes, d_reasons = evaluate_data_validity(
        message=user_message,
        result_level=fnn_level,
        hours=hours,
        sas_answers=sas_answers,
    )

    # Bước 2: Kiểm tra sơ bộ phạm vi giáo dục từ câu hỏi người dùng (P)
    p_input_val, p_input_codes, p_input_reasons = precheck_user_intent_scope(user_message)

    # Nếu D = 0 hoặc P_input = 0 -> Chặn kết luận cá nhân hóa sớm và cung cấp hỗ trợ thay thế an toàn
    if d_val == 0 or p_input_val == 0:
        bram_res = abstention_mechanism(d_val, 1, 1, p_input_val, 1)
        all_codes = list(dict.fromkeys(d_codes + p_input_codes))
        all_reasons = d_reasons + p_input_reasons
        safe_payload = build_safe_abstention_response(
            fnn_level=fnn_level,
            hours=hours,
            symptoms=symptoms,
            failed_conditions=bram_res["failed_conditions"],
            rejection_codes=all_codes,
            is_crisis=False,
        )
        return {
            "reply": safe_payload["reply"],
            "bram_technical": {
                **bram_res,
                "rejection_codes": all_codes,
                "rejection_reasons": all_reasons,
                "recommendation_codes": ["N/A (Từ chối kết luận cá nhân hóa - dùng khuyến nghị chung)"],
                "scientific_sources": [],
                "human_support_required": "R08" in all_codes,
            },
            "student_display": safe_payload["student_display"],
        }

    # Bước 3: Gọi Gemini với File Search Store (16 PDF thẩm định) để tạo dự thảo tư vấn
    generation_prompt = f"""
--- HỒ SƠ HỌC SINH (KHÔNG ĐƯỢC THAY ĐỔI KẾT QUẢ FNN) ---
- Mức độ nguy cơ từ mô hình FNN (bắt buộc giữ nguyên): {fnn_level}
- Thời gian sử dụng điện thoại trung bình: {hours} giờ/ngày
- Các biểu hiện nổi bật ghi nhận: {', '.join(symptoms) if symptoms else 'Chưa ghi nhận biểu hiện nổi bật'}

--- LỊCH SỬ TRÒ CHUYỆN GẦN ĐÂY ---
{history_str}

--- TIN NHẮN CỦA HỌC SINH ---
"{user_message}"

Yêu cầu bắt buộc:
1. Chỉ dựa trên các tài liệu khoa học trong File Search Store để đưa ra gợi ý giáo dục phù hợp.
2. Giữ nguyên mức độ nguy cơ FNN là "{fnn_level}"; không nâng, hạ hoặc chẩn đoán bệnh lý/nghiện điện thoại.
3. Không khẳng định quan hệ nhân quả nếu bằng chứng chỉ phản ánh mối tương quan.
4. Viết phản hồi ngắn gọn (3–5 câu), ấm áp, khích lệ, không phán xét, không cực đoan, kèm lưu ý đây chỉ là hỗ trợ giáo dục học đường.
"""
    try:
        candidate_reply, retrieved_sources = await generate_with_file_search_store(
            prompt=generation_prompt,
            system_instruction=system_instruction,
        )
    except Exception as gen_err:
        bram_res = abstention_mechanism(d_val, 1, 0, 1, 1)
        safe_payload = build_safe_abstention_response(
            fnn_level=fnn_level,
            hours=hours,
            symptoms=symptoms,
            failed_conditions=["E"],
            rejection_codes=["R05"],
            is_crisis=False,
        )
        return {
            "reply": safe_payload["reply"],
            "bram_technical": {
                **bram_res,
                "rejection_codes": ["R05"],
                "rejection_reasons": [f"Gián đoạn truy xuất kho tri thức File Search Store: {gen_err}"],
                "recommendation_codes": ["N/A"],
                "scientific_sources": [],
                "human_support_required": False,
            },
            "student_display": safe_payload["student_display"],
        }

    # Bước 4: Kiểm duyệt độc lập (tất định + ngữ nghĩa)
    det_check = deterministic_output_guard(
        draft_text=candidate_reply,
        fnn_level=fnn_level,
        retrieved_sources=retrieved_sources,
    )
    sem_check = await run_semantic_bram_audit(
        user_message=user_message,
        fnn_level=fnn_level,
        hours=hours,
        symptoms=symptoms,
        candidate_reply=candidate_reply,
        retrieved_sources=det_check["matched_sources"],
    )

    # Kết hợp thận trọng: điều kiện chỉ bằng 1 khi cả bộ kiểm tra tất định và kiểm duyệt ngữ nghĩa đều xác nhận 1
    final_D = int(d_val == 1 and sem_check.D_valid == 1)
    final_C = int(det_check["C"] == 1 and sem_check.C_consistent == 1)
    final_E = int(det_check["E"] == 1 and sem_check.E_evidenced == 1)
    final_P = int(det_check["P"] == 1 and sem_check.P_pedagogical == 1)
    final_S = int(det_check["S"] == 1 and sem_check.S_safe == 1)

    # Bước 5: Tính R bằng hàm Boolean độc lập
    bram_res = abstention_mechanism(final_D, final_C, final_E, final_P, final_S)

    combined_codes = list(
        dict.fromkeys(det_check["violated_codes"] + [c for c in sem_check.violated_codes if c in REJECTION_CATALOG])
    )
    # Bảo đảm mọi điều kiện bằng 0 đều có mã từ chối tương ứng
    condition_default_code = {"D": "R02", "C": "R04", "E": "R05", "P": "R07", "S": "R10"}
    for cond in bram_res["failed_conditions"]:
        if not any(REJECTION_CATALOG.get(c, {}).get("condition") == cond for c in combined_codes):
            combined_codes.append(condition_default_code[cond])

    combined_reasons = det_check["notes"] + ([sem_check.audit_notes] if sem_check.audit_notes else [])

    # Bước 6: Xử lý kết quả R = 0 (ACCEPT) hoặc R = 1 (ABSTAIN)
    if bram_res["rejection_value"] == 0:
        return {
            "reply": candidate_reply,
            "bram_technical": {
                **bram_res,
                "rejection_codes": [],
                "rejection_reasons": [],
                "recommendation_codes": [
                    "KB-GROUNDED (Trích xuất trực tiếp từ File Search Store; chưa gắn mã REC rời)"
                ],
                "scientific_sources": det_check["matched_sources"],
                "human_support_required": False,
            },
            "student_display": {
                "objective_observation": f"Mức sàng lọc FNN: {fnn_level} | Thời gian dùng: {hours} giờ/ngày.",
                "result_or_abstention_explanation": f"Kết quả sàng lọc hiện tại của em ở mức {fnn_level}.",
                "educational_recommendation": candidate_reply,
                "practical_goal": "Lựa chọn một thay đổi nhỏ, phù hợp với lịch học tập và nghỉ ngơi của em.",
                "encouragement": "Em đang chủ động lắng nghe và điều chỉnh thói quen số của mình rất tích cực!",
                "system_disclaimer": DEFAULT_SYSTEM_DISCLAIMER,
            },
        }

    safe_payload = build_safe_abstention_response(
        fnn_level=fnn_level,
        hours=hours,
        symptoms=symptoms,
        failed_conditions=bram_res["failed_conditions"],
        rejection_codes=combined_codes,
        is_crisis=False,
    )
    return {
        "reply": safe_payload["reply"],
        "bram_technical": {
            **bram_res,
            "rejection_codes": combined_codes,
            "rejection_reasons": combined_reasons,
            "recommendation_codes": ["N/A (Đã chặn dự thảo vi phạm và dùng phản hồi thay thế an toàn)"],
            "scientific_sources": det_check["matched_sources"],
            "human_support_required": ("R08" in combined_codes or fnn_level == "Cao"),
        },
        "student_display": safe_payload["student_display"],
    }
