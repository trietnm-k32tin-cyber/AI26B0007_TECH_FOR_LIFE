from contextlib import asynccontextmanager
import datetime
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import string
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, firestore as fb_firestore, messaging
import joblib
import numpy as np
import openvino as ov
from sklearn.feature_extraction.text import TfidfVectorizer
from supabase import Client, create_client

from api.schemas import (
    AuthCodeRequest,
    LoginRequest,
    MicroSurveyRequest,
    MicroSurveyResponse,
    NightlyEvalRequest,
    NightlyEvalResponse,
    PredictionRequest,
    PredictionResponse,
    RegisterRequest,
    UserSyncRequest,
)

try:
    from api.gemini_advisor import (
        init_gemini_advisor,
        router as gemini_advisor_router,
    )
except ImportError:
    try:
        from api.routers.gemini_advisor import (
            init_gemini_advisor,
            router as gemini_advisor_router,
        )
    except ImportError:
        from gemini_advisor import (
            init_gemini_advisor,
            router as gemini_advisor_router,
        )

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(BASE_DIR, "api")


def _resolve_existing_path(*candidates: str) -> str:
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return candidates[0]


def _resolve_dir(*candidates: str) -> str:
    for d in candidates:
        if d and os.path.isdir(d):
            return d
    return candidates[0]


OPENVINO_DIR = _resolve_dir(
    os.path.join(BASE_DIR, "model_artifacts", "openvino_ir_models"),
    os.path.join(API_DIR, "model_artifacts", "openvino_ir_models"),
    os.path.join(BASE_DIR, "openvino_ir_models"),
    os.path.join(API_DIR, "openvino_ir_models"),
)

SCALERS_DIR = _resolve_dir(
    os.path.join(BASE_DIR, "model_artifacts", "scalers"),
    os.path.join(API_DIR, "model_artifacts", "scalers"),
    os.path.join(BASE_DIR, "scalers"),
    os.path.join(API_DIR, "scalers"),
)

MEDICAL_KB_PATH = _resolve_existing_path(
    os.path.join(BASE_DIR, "medical_kb.json"),
    os.path.join(API_DIR, "medical_kb.json"),
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client | None = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Lỗi Supabase: {e}")

COMPILED_MODELS: list[Any] = []
SCALERS: list[Any] = []
N_SPLITS = 10

MEDICAL_KB: list[dict[str, Any]] = []
VECTORIZER: TfidfVectorizer | None = None
MEDICAL_KB_MATRIX: Any = None


# --- BẢO MẬT MẬT KHẨU & TÊN ĐĂNG NHẬP ---
def hash_password(password: str) -> str:
    """Băm mật khẩu bằng PBKDF2-HMAC-SHA256 kèm salt ngẫu nhiên."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Đối chiếu mật khẩu người dùng nhập với chuỗi băm trong Supabase."""
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, hash_hex = stored_hash.split("$", 1)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    )
    return hmac.compare_digest(dk.hex(), hash_hex)


def validate_and_clean_username(raw_username: str) -> str:
    clean = (raw_username or "").strip().lower()
    if not re.match(r"^[a-z0-9_.]{3,30}$", clean):
        raise HTTPException(
            status_code=400,
            detail=(
                "Tên đăng nhập phải từ 3–30 ký tự, chỉ gồm chữ cái không dấu,"
                " số, dấu chấm (.) hoặc gạch dưới (_)."
            ),
        )
    return clean


def sanitize_user_record(row: dict[str, Any]) -> dict[str, Any]:
    """Loại bỏ password_hash trước khi trả dữ liệu người dùng về frontend."""
    return {k: v for k, v in row.items() if k != "password_hash"}


def fetch_user_survey_history(user_code: str) -> list[dict[str, Any]]:
    """Lấy danh sách lịch sử khảo sát của người dùng từ bảng survey_results."""
    if not supabase or not user_code:
        return []
    try:
        res = (
            supabase.table("survey_results")
            .select("*")
            .eq("user_code", user_code)
            .order("created_at", desc=True)
            .execute()
        )
        level_map = {0: "Thấp", 1: "Trung bình", 2: "Cao"}
        formatted = []
        for row in res.data or []:
            lvl = (
                row.get("Level")
                if row.get("Level") is not None
                else row.get("addiction", 1)
            )
            formatted.append({
                "id": row.get("id"),
                "date": row.get("created_at", ""),
                "prediction": level_map.get(lvl, "Trung bình"),
                "avgHours": row.get("tg_sudung_dt", 0),
                "totalScore": row.get("Tong", 0),
            })
        return formatted
    except Exception as e:
        print(f"⚠️ Lỗi tải lịch sử khảo sát từ Supabase: {e}")
        return []


def normalize_user_code(raw_code: str | None) -> str | None:
    if not raw_code or not raw_code.strip():
        return None
    cleaned = raw_code.strip()
    if cleaned.upper().startswith("HS-"):
        return cleaned.upper()
    return cleaned


def safe_supabase_insert(table_name: str, payload: dict[str, Any]):
    if not supabase:
        return None
    data = {k: v for k, v in payload.items() if v is not None}
    for _ in range(6):
        try:
            res = supabase.table(table_name).insert(data).execute()
            print(f"✅ Đã lưu dữ liệu vào bảng {table_name}!")
            return res
        except Exception as e:
            err_str = str(e)
            match = re.search(r"Could not find the '([^']+)' column", err_str)
            if match:
                missing_col = match.group(1)
                if missing_col in data:
                    print(
                        f"⚠️ Bảng {table_name} chưa có cột '{missing_col}', tự động bỏ qua"
                        " và lưu lại..."
                    )
                    data.pop(missing_col, None)
                    continue
            print(f"❌ Lỗi lưu bảng {table_name}: {err_str}")
            return None
    return None


def safe_supabase_update(
    table_name: str, payload: dict[str, Any], match_col: str, match_val: str
):
    if not supabase:
        return None
    data = {k: v for k, v in payload.items() if v is not None and k != match_col}
    if not data:
        return None
    for _ in range(6):
        try:
            res = (
                supabase.table(table_name)
                .update(data)
                .eq(match_col, match_val)
                .execute()
            )
            print(f"✅ Đã cập nhật dữ liệu trong bảng {table_name}!")
            return res
        except Exception as e:
            err_str = str(e)
            match = re.search(r"Could not find the '([^']+)' column", err_str)
            if match:
                missing_col = match.group(1)
                if missing_col in data:
                    data.pop(missing_col, None)
                    if not data:
                        return None
                    continue
            print(f"❌ Lỗi cập nhật bảng {table_name}: {err_str}")
            return None
    return None


def upsert_user_supabase(
    user_code: str | None,
    uid: str | None = None,
    email: str | None = None,
    name: str | None = None,
    school: str | None = None,
    grade: str | None = None,
    gender: str | None = None,
):
    if not supabase or not user_code:
        return

    now_iso = datetime.datetime.now().isoformat()
    payload: dict[str, Any] = {
        "user_code": user_code,
        "uid": uid,
        "email": email,
        "name": name,
        "school": school,
        "grade": grade,
        "gender": gender,
    }

    try:
        existing = (
            supabase.table("users")
            .select("user_code")
            .eq("user_code", user_code)
            .execute()
        )
        if not existing.data:
            payload["created_at"] = now_iso
            safe_supabase_insert("users", payload)
        else:
            payload["updated_at"] = now_iso
            safe_supabase_update("users", payload, "user_code", user_code)
    except Exception as e:
        print(f"⚠️ Thử lưu trực tiếp vào bảng users do: {e}")
        payload["created_at"] = now_iso
        safe_supabase_insert("users", payload)


def generate_unique_user_code() -> str:
    while True:
        code = "HS-" + "".join(
            random.choices(string.ascii_uppercase + string.digits, k=5)
        )
        if supabase:
            try:
                res = (
                    supabase.table("users")
                    .select("user_code")
                    .eq("user_code", code)
                    .execute()
                )
                if not res.data:
                    return code
            except Exception:
                return code
        else:
            return code


# --- KHỞI TẠO FIREBASE ADMIN (NẾU CÓ) ---
firestore_db = None
FIREBASE_CRED_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
try:
    if not firebase_admin._apps:
        cred_file = _resolve_existing_path(
            os.path.join(BASE_DIR, "serviceAccountKey.json"),
            os.path.join(API_DIR, "serviceAccountKey.json"),
        )
        if FIREBASE_CRED_JSON:
            cred_dict = json.loads(FIREBASE_CRED_JSON)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        elif os.path.exists(cred_file):
            cred = credentials.Certificate(cred_file)
            firebase_admin.initialize_app(cred)
    if firebase_admin._apps:
        firestore_db = fb_firestore.client()
        print("✅ Đã kết nối Cloud Firestore thành công!")
except Exception as e:
    print(f"⚠️ Chưa khởi tạo Firebase Admin: {e}")


# --- CHUẨN BỊ VECTOR & CHẠY SUY LUẬN OPENVINO 10-FOLD ---
def _prepare_feature_vector(
    tg_sudung_dt: float, q_list: list[int], expected_dim: int | None = None
) -> np.ndarray:
    q_arr = np.array(q_list, dtype=np.float32)
    q_mean = float(np.mean(q_arr))
    q_std = float(np.std(q_arr))
    q_max = float(np.max(q_arr))

    features_14 = np.array(
        [[float(tg_sudung_dt), *q_list, q_mean, q_std, q_max]],
        dtype=np.float32,
    )

    if expected_dim is None or expected_dim == features_14.shape[1]:
        return features_14

    if expected_dim == 11:
        return np.array([[float(tg_sudung_dt), *q_list]], dtype=np.float32)

    if expected_dim == 10:
        return np.array([q_list], dtype=np.float32)

    if features_14.shape[1] > expected_dim:
        return features_14[:, :expected_dim]

    pad_width = expected_dim - features_14.shape[1]
    return np.pad(features_14, ((0, 0), (0, pad_width)), mode="constant")


def run_openvino_inference(tg_sudung_dt: float, q_list: list[int]):
    tong_diem = int(sum(q_list))
    total_probs = np.zeros((1, 3), dtype=np.float32)

    if COMPILED_MODELS and SCALERS:
        valid_folds = 0
        num_pairs = min(len(COMPILED_MODELS), len(SCALERS))
        for idx in range(num_pairs):
            try:
                expected_dim = getattr(SCALERS[idx], "n_features_in_", None)
                vec = _prepare_feature_vector(tg_sudung_dt, q_list, expected_dim)
                scaled_vec = SCALERS[idx].transform(vec).astype(np.float32)
                output_layer = COMPILED_MODELS[idx].output(0)
                fold_prob = np.asarray(
                    COMPILED_MODELS[idx]([scaled_vec])[output_layer],
                    dtype=np.float32,
                )
                if fold_prob.ndim == 1:
                    fold_prob = fold_prob.reshape(1, -1)
                total_probs += fold_prob[:, :3]
                valid_folds += 1
            except Exception as err:
                print(f"⚠️ Lỗi suy luận ở fold {idx + 1}: {err}")

        if valid_folds > 0:
            total_probs = total_probs / valid_folds
            predicted_class = int(np.argmax(total_probs, axis=1)[0])
            return predicted_class, total_probs, tong_diem

    if tong_diem <= 20:
        predicted_class = 0
    elif tong_diem <= 35:
        predicted_class = 1
    else:
        predicted_class = 2
    total_probs[0][predicted_class] = 1.0
    return predicted_class, total_probs, tong_diem


def compute_tipping_point(q_list: list[int]) -> float:
    for step in range(1, 21):
        test_hours = step * 0.5
        pred_cls, probs, _ = run_openvino_inference(test_hours, q_list)
        high_prob = float(probs[0][2]) if len(COMPILED_MODELS) > 0 else 0.0
        if pred_cls == 2 or high_prob >= 0.5:
            return round(test_hours, 1)
    return 5.0


def get_latest_sas_from_firestore(uid: str) -> tuple[list[int], bool, list[str]]:
    q_list = [3] * 10
    has_prior = False
    shap_causes: list[str] = []
    if firestore_db and uid:
        try:
            docs = (
                firestore_db.collection("users")
                .document(uid)
                .collection("survey_history")
                .order_by("date", direction=fb_firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict() or {}
                saved_answers = data.get("sas_answers")
                if isinstance(saved_answers, list) and len(saved_answers) == 10:
                    q_list = [int(x) for x in saved_answers]
                    has_prior = True
                raw_causes = data.get("shap_root_causes", [])
                if isinstance(raw_causes, list):
                    shap_causes = [str(c) for c in raw_causes]
        except Exception as e:
            print(f"⚠️ Lỗi đọc SAS-SV từ Firestore: {e}")
    return q_list, has_prior, shap_causes


def evaluate_threshold_rule_based(
    result_str: str,
    predicted_class: int,
    usage_hours: float,
    tong_diem: int,
    tipping_hours: float,
    survey_type: str = "initial",
) -> tuple[float, str]:
    if predicted_class == 2:
        raw_threshold = min(max(usage_hours * 0.8, 2.0), tipping_hours, 4.0)
    elif predicted_class == 1:
        raw_threshold = min(max(usage_hours, 2.5), tipping_hours, 5.0)
    else:
        raw_threshold = min(max(usage_hours, 3.0), tipping_hours, 6.0)

    threshold = round(max(1.5, min(raw_threshold, 6.5)) * 2) / 2
    mode_text = "đánh giá cuối tuần" if survey_type == "weekly" else "khảo sát ban đầu"
    explanation = (
        f"Từ {mode_text} với mức sàng lọc {result_str} ({tong_diem}/60 điểm SAS-SV, "
        f"thời gian dùng {usage_hours}h/ngày, điểm bùng phát {tipping_hours}h/ngày), "
        f"hệ thống gợi ý ngưỡng theo dõi {threshold} giờ/ngày để duy trì cân bằng học tập."
    )
    return threshold, explanation


@asynccontextmanager
async def lifespan(app: FastAPI):
    global COMPILED_MODELS, SCALERS, MEDICAL_KB, VECTORIZER, MEDICAL_KB_MATRIX
    COMPILED_MODELS = []
    SCALERS = []
    MEDICAL_KB = []
    VECTORIZER = None
    MEDICAL_KB_MATRIX = None

    print("🚀 Đang khởi tạo hệ thống...")
    init_gemini_advisor(supabase, BASE_DIR)

    try:
        if os.path.exists(MEDICAL_KB_PATH):
            with open(MEDICAL_KB_PATH, "r", encoding="utf-8") as f:
                loaded_kb = json.load(f)
            if isinstance(loaded_kb, list) and loaded_kb:
                MEDICAL_KB = loaded_kb
                corpus = [
                    f"{item.get('title', '')} {item.get('content', '')}"
                    for item in MEDICAL_KB
                ]
                VECTORIZER = TfidfVectorizer()
                MEDICAL_KB_MATRIX = VECTORIZER.fit_transform(corpus)
                print(f"✅ Đã nạp {len(MEDICAL_KB)} mục kho tri thức cục bộ!")

        core = ov.Core()
        for fold in range(1, N_SPLITS + 1):
            xml_path = _resolve_existing_path(
                os.path.join(OPENVINO_DIR, f"fnn_model_fold_{fold}.xml"),
                os.path.join(BASE_DIR, "model_artifacts", "openvino_ir_models", f"fnn_model_fold_{fold}.xml"),
                os.path.join(API_DIR, "model_artifacts", "openvino_ir_models", f"fnn_model_fold_{fold}.xml"),
                os.path.join(BASE_DIR, "openvino_ir_models", f"fnn_model_fold_{fold}.xml"),
                os.path.join(API_DIR, "openvino_ir_models", f"fnn_model_fold_{fold}.xml"),
            )
            scaler_path = _resolve_existing_path(
                os.path.join(SCALERS_DIR, f"scaler_fold_{fold}.pkl"),
                os.path.join(BASE_DIR, "model_artifacts", "scalers", f"scaler_fold_{fold}.pkl"),
                os.path.join(API_DIR, "model_artifacts", "scalers", f"scaler_fold_{fold}.pkl"),
                os.path.join(BASE_DIR, "scalers", f"scaler_fold_{fold}.pkl"),
                os.path.join(API_DIR, "scalers", f"scaler_fold_{fold}.pkl"),
            )

            if os.path.exists(xml_path) and os.path.exists(scaler_path):
                COMPILED_MODELS.append(
                    core.compile_model(model=xml_path, device_name="CPU")
                )
                SCALERS.append(joblib.load(scaler_path))
            else:
                print(f"⚠️ Thiếu file fold {fold}: xml={xml_path}, scaler={scaler_path}")

        print(f"✅ Đã nạp {len(COMPILED_MODELS)}/{N_SPLITS} fold OpenVINO models!")
    except Exception as e:
        print(f"⚠️ Cảnh báo khởi tạo: {e}")

    yield
    print("Tắt Server...")


app = FastAPI(
    title="Smartphone Addiction OpenVINO Ensemble API",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gemini_advisor_router)


# --- ĐĂNG KÝ & ĐĂNG NHẬP TÀI KHOẢN SUPABASE ---
@app.post("/api/auth/register")
async def register_user(req: RegisterRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Chưa kết nối CSDL Supabase")

    clean_username = validate_and_clean_username(req.username)
    if not req.password or len(req.password) < 6:
        raise HTTPException(
            status_code=400, detail="Mật khẩu phải có ít nhất 6 ký tự."
        )

    try:
        existing = (
            supabase.table("users")
            .select("user_code")
            .eq("username", clean_username)
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=400,
                detail="Tên đăng nhập đã tồn tại, vui lòng chọn tên khác!",
            )

        new_code = generate_unique_user_code()
        now_iso = datetime.datetime.now().isoformat()
        new_user_row = {
            "user_code": new_code,
            "uid": new_code,
            "username": clean_username,
            "password_hash": hash_password(req.password),
            "name": (req.name or "").strip(),
            "grade": "11",
            "gender": "Nam",
            "created_at": now_iso,
        }

        res = supabase.table("users").insert(new_user_row).execute()
        created = res.data[0] if res.data else new_user_row

        return {
            "status": "success",
            "user_info": sanitize_user_record(created),
            "session_history": [],
        }
    except HTTPException as http_ex:
        raise http_ex
    except Exception as err:
        err_msg = str(err)
        if "username" in err_msg or "password_hash" in err_msg:
            raise HTTPException(
                status_code=500,
                detail="Bảng 'users' trên Supabase chưa có cột 'username' hoặc 'password_hash'. Vui lòng chạy SQL migration!",
            )
        print(f"❌ Lỗi đăng ký tài khoản: {err}")
        raise HTTPException(status_code=500, detail=f"Lỗi đăng ký: {err_msg}")


@app.post("/api/auth/login")
async def login_user(req: LoginRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Chưa kết nối CSDL Supabase")

    clean_username = (req.username or "").strip().lower()
    if not clean_username or not req.password:
        raise HTTPException(
            status_code=400, detail="Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu."
        )

    try:
        user_res = (
            supabase.table("users")
            .select("*")
            .eq("username", clean_username)
            .execute()
        )
        if not user_res.data:
            raise HTTPException(
                status_code=401,
                detail="Tên đăng nhập hoặc mật khẩu không chính xác!",
            )

        user_row = user_res.data[0]
        if not verify_password(req.password, user_row.get("password_hash")):
            raise HTTPException(
                status_code=401,
                detail="Tên đăng nhập hoặc mật khẩu không chính xác!",
            )

        user_code = user_row.get("user_code")
        history = fetch_user_survey_history(user_code)

        return {
            "status": "success",
            "user_info": sanitize_user_record(user_row),
            "session_history": history,
        }
    except HTTPException as http_ex:
        raise http_ex
    except Exception as err:
        print(f"❌ Lỗi đăng nhập: {err}")
        raise HTTPException(status_code=500, detail=f"Lỗi đăng nhập: {str(err)}")


@app.get("/api/users/{user_code}/profile")
async def get_user_profile_and_history(user_code: str):
    if not supabase:
        raise HTTPException(status_code=500, detail="Chưa kết nối CSDL Supabase")

    clean_code = normalize_user_code(user_code)
    try:
        user_res = (
            supabase.table("users")
            .select("*")
            .eq("user_code", clean_code)
            .execute()
        )
        if not user_res.data:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")

        history = fetch_user_survey_history(clean_code)
        return {
            "user_info": sanitize_user_record(user_res.data[0]),
            "session_history": history,
        }
    except HTTPException as http_ex:
        raise http_ex
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Lỗi tải dữ liệu: {str(err)}")


@app.post("/api/auth/code")
async def handle_user_code(req: AuthCodeRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Chưa kết nối CSDL Supabase")

    try:
        if req.user_code and req.user_code.strip():
            clean_code = normalize_user_code(req.user_code)
            user_res = (
                supabase.table("users")
                .select("*")
                .eq("user_code", clean_code)
                .execute()
            )
            if not user_res.data:
                raise HTTPException(
                    status_code=404, detail="Mã người dùng không tồn tại!"
                )

            user_info = sanitize_user_record(user_res.data[0])
            history_res = (
                supabase.table("survey_results")
                .select("*")
                .eq("user_code", clean_code)
                .order("created_at", desc=False)
                .execute()
            )

            return {
                "is_new": False,
                "user_info": user_info,
                "session_history": history_res.data or [],
                "total_sessions": len(history_res.data or []),
            }
        else:
            if not req.name or not req.school:
                raise HTTPException(
                    status_code=400, detail="Vui lòng cung cấp Họ tên và Trường học."
                )

            new_code = generate_unique_user_code()
            new_user = {
                "user_code": new_code,
                "name": req.name,
                "school": req.school,
                "grade": req.grade or "11",
                "gender": req.gender or "Nam",
                "created_at": datetime.datetime.now().isoformat(),
            }
            safe_supabase_insert("users", new_user)
            return {
                "is_new": True,
                "user_info": new_user,
                "session_history": [],
                "total_sessions": 0,
            }
    except HTTPException as http_ex:
        raise http_ex
    except Exception as err:
        print(f"❌ Lỗi xử lý user_code: {err}")
        raise HTTPException(status_code=500, detail=f"Lỗi Server: {str(err)}")


@app.post("/api/users/sync")
async def sync_user_profile(req: UserSyncRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Chưa kết nối CSDL Supabase")

    code = normalize_user_code(req.user_code or req.uid)
    upsert_user_supabase(
        user_code=code,
        uid=req.uid,
        email=req.email,
        name=req.name,
        school=req.school,
        grade=req.grade,
        gender=req.gender,
    )
    return {"status": "success", "user_code": code}


@app.get("/api/stats")
async def get_stats():
    total_users = 0
    if supabase:
        try:
            res = (
                supabase.table("survey_results").select("id", count="exact").execute()
            )
            total_users = res.count if res.count is not None else 0
        except Exception as e:
            print(f"❌ Lỗi đếm số lượng survey_results: {e}")
    return {"total_users": total_users}


def analyze_feature_contributions(input_features_dict: dict[str, Any]) -> list[str]:
    tg_sudung = float(
        input_features_dict.get(
            "tg_sudung_dt", input_features_dict.get("hours", 0)
        )
    )

    causes: list[str] = []
    if tg_sudung >= 5.0:
        causes.append(f"Thời gian sử dụng điện thoại {tg_sudung} giờ/ngày")
    if int(input_features_dict.get("Q8", 0) or 0) >= 4:
        causes.append("Thường xuyên kiểm tra điện thoại vì sợ bỏ lỡ thông tin")
    if int(input_features_dict.get("Q9", 0) or 0) >= 4:
        causes.append("Dùng điện thoại lâu hơn kế hoạch dự kiến")
    if int(input_features_dict.get("Q4", 0) or 0) >= 4:
        causes.append("Cảm thấy khó chịu hoặc bồn chồn khi không có điện thoại")
    if int(input_features_dict.get("Q7", 0) or 0) >= 4:
        causes.append("Khó dừng sử dụng dù đã ảnh hưởng tới nhịp sinh hoạt/học tập")
    if int(input_features_dict.get("Q3", 0) or 0) >= 4:
        causes.append("Cảm thấy mỏi cổ hoặc cổ tay khi dùng thiết bị lâu")

    if not causes:
        causes = [
            f"Thời gian sử dụng {tg_sudung}h/ngày",
            "Cần duy trì khung giờ học tập và nghỉ ngơi rõ ràng",
        ]

    return causes[:3]


@app.post("/api/predict", response_model=PredictionResponse)
async def predict_addiction(request: PredictionRequest):
    q_list = [
        request.Q1,
        request.Q2,
        request.Q3,
        request.Q4,
        request.Q5,
        request.Q6,
        request.Q7,
        request.Q8,
        request.Q9,
        request.Q10,
    ]
    predicted_class, total_probs, tong_diem = run_openvino_inference(
        request.tg_sudung_dt, q_list
    )

    mapping = {0: "Thấp", 1: "Trung bình", 2: "Cao"}
    result_str = mapping.get(predicted_class, "Trung bình")

    low_conf = float(round(total_probs[0][0], 4)) if COMPILED_MODELS else 0.33
    med_conf = float(round(total_probs[0][1], 4)) if COMPILED_MODELS else 0.34
    high_conf = float(round(total_probs[0][2], 4)) if COMPILED_MODELS else 0.33

    survey_dict: dict[str, Any] = {f"Q{i+1}": q_list[i] for i in range(10)}
    survey_dict["tg_sudung_dt"] = request.tg_sudung_dt
    shap_causes = analyze_feature_contributions(survey_dict)
    tipping_hours = compute_tipping_point(q_list)

    survey_type = request.survey_type or "initial"
    threshold_hours, summary_explanation = evaluate_threshold_rule_based(
        result_str=result_str,
        predicted_class=predicted_class,
        usage_hours=request.tg_sudung_dt,
        tong_diem=tong_diem,
        tipping_hours=tipping_hours,
        survey_type=survey_type,
    )

    clean_user_code = normalize_user_code(request.user_code or request.uid)

    if supabase:
        upsert_user_supabase(
            user_code=clean_user_code,
            uid=request.uid,
            email=request.email,
            name=request.name,
            school=request.Truong,
            grade=request.Khoi,
            gender=request.Phai,
        )

        safe_supabase_insert(
            "survey_results",
            {
                "user_code": clean_user_code,
                "email": request.email,
                "name": request.name,
                "Truong": request.Truong,
                "Khoi": request.Khoi,
                "Phai": request.Phai,
                "tg_sudung_dt": request.tg_sudung_dt,
                "Tong": tong_diem,
                "addiction": predicted_class,
                "Level": predicted_class,
                "Q1": request.Q1,
                "Q2": request.Q2,
                "Q3": request.Q3,
                "Q4": request.Q4,
                "Q5": request.Q5,
                "Q6": request.Q6,
                "Q7": request.Q7,
                "Q8": request.Q8,
                "Q9": request.Q9,
                "Q10": request.Q10,
                "created_at": datetime.datetime.now().isoformat(),
            },
        )

    if firestore_db and request.uid:
        try:
            user_ref = firestore_db.collection("users").document(request.uid)
            user_ref.collection("survey_history").add({
                "uid": request.uid,
                "name": request.name,
                "school": request.Truong,
                "grade": request.Khoi,
                "gender": request.Phai,
                "avgHours": request.tg_sudung_dt,
                "weekId": request.week_id,
                "surveyType": survey_type,
                "sas_answers": q_list,
                "shap_root_causes": shap_causes,
                "tippingPointHours": tipping_hours,
                "thresholdHours": threshold_hours,
                "geminiExplanation": summary_explanation,
                "totalScore": tong_diem,
                "predictedLevel": predicted_class,
                "prediction": result_str,
                "advice": summary_explanation,
                "date": datetime.datetime.now().isoformat(),
            })

            user_ref.collection("adaptive_config").document("current").set(
                {
                    "tipping_point_hours": tipping_hours,
                    "threshold_tomorrow": threshold_hours,
                    "shap_root_causes": shap_causes,
                    "shield_enabled": predicted_class == 2,
                    "updatedAt": datetime.datetime.now().isoformat(),
                },
                merge=True,
            )
        except Exception as e:
            print(f"⚠️ Lỗi đồng bộ Firestore: {e}")

    return PredictionResponse(
        predicted_level=predicted_class,
        confidence_scores={
            "Thấp": low_conf,
            "Trung bình": med_conf,
            "Cao": high_conf,
        },
        result=result_str,
        advice=summary_explanation,
        tipping_point_hours=tipping_hours,
        threshold_hours=threshold_hours,
        gemini_explanation=summary_explanation,
        shap_root_causes=shap_causes,
    )


@app.post("/api/app/nightly-eval", response_model=NightlyEvalResponse)
async def evaluate_nightly_usage(req: NightlyEvalRequest):
    q_list, _, shap_causes = get_latest_sas_from_firestore(req.uid)

    today_cls, _, _ = run_openvino_inference(req.today_hours, q_list)
    mapping = {0: "Thấp", 1: "Trung bình", 2: "Cao"}
    today_result = mapping.get(today_cls, "Trung bình")

    tipping_hours = compute_tipping_point(q_list)
    raw_threshold = (
        min(req.today_hours, tipping_hours)
        if req.today_hours >= 1.5
        else tipping_hours
    )
    threshold_tomorrow = round(max(1.5, raw_threshold), 1)

    if firestore_db and req.uid:
        try:
            firestore_db.collection("users").document(req.uid).collection(
                "adaptive_config"
            ).document("current").set(
                {
                    "last_today_hours": req.today_hours,
                    "last_today_level": today_cls,
                    "tipping_point_hours": tipping_hours,
                    "threshold_tomorrow": threshold_tomorrow,
                    "shap_root_causes": shap_causes,
                    "top_apps_yesterday": req.top_apps,
                    "updatedAt": datetime.datetime.now().isoformat(),
                },
                merge=True,
            )
        except Exception as e:
            print(f"⚠️ Lỗi lưu adaptive_config buổi tối: {e}")

    return NightlyEvalResponse(
        today_level=today_cls,
        today_result=today_result,
        tipping_point_hours=tipping_hours,
        threshold_tomorrow=threshold_tomorrow,
        q4_score=q_list[3],
        q8_score=q_list[7],
        shap_root_causes=shap_causes,
    )


@app.post("/api/app/micro-survey-eval", response_model=MicroSurveyResponse)
async def evaluate_micro_survey(req: MicroSurveyRequest):
    if req.mood_status == "studying":
        return MicroSurveyResponse(
            evaluated=False,
            predicted_level=0,
            result="Đang học tập",
            trigger_focus_mode=False,
            activate_shield=False,
            ai_alert_message=(
                "Hệ thống đã ghi nhận bạn đang học tập và tạm hoãn nhắc nhở để"
                " không làm phiền bạn."
            ),
            shap_root_causes=[],
            has_prior_survey=True,
        )

    q_list, has_prior, shap_causes = get_latest_sas_from_firestore(req.uid)
    if not shap_causes:
        survey_dict: dict[str, Any] = {f"Q{i+1}": q_list[i] for i in range(10)}
        survey_dict["tg_sudung_dt"] = req.current_hours
        shap_causes = analyze_feature_contributions(survey_dict)

    predicted_class, _, _ = run_openvino_inference(req.current_hours, q_list)
    mapping = {0: "Thấp", 1: "Trung bình", 2: "Cao"}
    result_str = mapping.get(predicted_class, "Trung bình")

    trigger_focus = predicted_class >= 1
    activate_shield = predicted_class == 2

    top_apps_str = (
        ", ".join(req.top_apps)
        if req.top_apps
        else "các ứng dụng mạng xã hội và giải trí"
    )

    if predicted_class == 2:
        alert_msg = (
            f"Nhắc nhở mức Cao: Bạn đã dùng {req.current_hours:.1f}h hôm nay "
            f"(nhiều nhất ở {top_apps_str}). Hệ thống đã bật chế độ hỗ trợ tập trung."
        )
    else:
        alert_msg = (
            f"Bạn đã dùng {req.current_hours:.1f}h hôm nay (mức {result_str}). "
            "Hãy nghỉ mắt vài phút và thử khung tập trung 25 phút nhé!"
        )

    if firestore_db and req.uid:
        try:
            firestore_db.collection("users").document(req.uid).collection(
                "adaptive_config"
            ).document("current").set(
                {
                    "shield_enabled": activate_shield,
                    "latest_ai_alert": alert_msg,
                    "latest_level": predicted_class,
                    "updatedAt": datetime.datetime.now().isoformat(),
                },
                merge=True,
            )
        except Exception as e:
            print(f"⚠️ Lỗi cập nhật trạng thái Khiên chặn: {e}")

    if req.fcm_token and firebase_admin._apps:
        try:
            msg = messaging.Message(
                notification=messaging.Notification(
                    title=(
                        "🚨 Nhắc nhở mức Cao từ T&Check"
                        if activate_shield
                        else "⚠️ Nhắc nhở nghỉ ngơi từ T&Check"
                    ),
                    body=alert_msg,
                ),
                data={
                    "action": (
                        "ACTIVATE_SHIELD" if activate_shield else "OPEN_FOCUS_MODE"
                    ),
                    "level": result_str,
                    "ai_message": alert_msg,
                },
                token=req.fcm_token,
            )
            messaging.send(msg)
        except Exception as e:
            print(f"⚠️ Không gửi được FCM: {e}")

    return MicroSurveyResponse(
        evaluated=True,
        predicted_level=predicted_class,
        result=result_str,
        trigger_focus_mode=trigger_focus,
        activate_shield=activate_shield,
        ai_alert_message=alert_msg,
        shap_root_causes=shap_causes,
        has_prior_survey=has_prior,
    )