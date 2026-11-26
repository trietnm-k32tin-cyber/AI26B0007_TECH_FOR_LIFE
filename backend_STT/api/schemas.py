from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthCodeRequest(BaseModel):
    user_code: str | None = None
    name: str | None = None
    school: str | None = None
    grade: str | None = None
    gender: str | None = None


class UserSyncRequest(BaseModel):
    uid: str
    user_code: str | None = None
    email: str | None = None
    name: str | None = None
    photo_url: str | None = None
    school: str | None = None
    grade: str | None = None
    gender: str | None = None


class PredictionRequest(BaseModel):
    uid: str | None = None
    user_code: str | None = None
    email: str | None = None
    source: str | None = "web"
    survey_type: str | None = "initial"
    name: str
    Truong: str
    Khoi: str
    Phai: str
    tg_sudung_dt: float
    week_id: str | None = None
    Q1: int
    Q2: int
    Q3: int
    Q4: int
    Q5: int
    Q6: int
    Q7: int
    Q8: int
    Q9: int
    Q10: int


class PredictionResponse(BaseModel):
    predicted_level: int
    confidence_scores: dict
    result: str
    advice: str
    tipping_point_hours: float = 5.0
    threshold_hours: float = 4.5
    gemini_explanation: str = ""
    shap_root_causes: list[str] = Field(default_factory=list)


class ThresholdGeminiSchema(BaseModel):
    threshold_hours: float
    explanation: str


class NightlyEvalRequest(BaseModel):
    uid: str
    email: str | None = None
    today_hours: float
    top_apps: list[str] = Field(default_factory=list)
    fcm_token: str | None = None


class NightlyEvalResponse(BaseModel):
    today_level: int
    today_result: str
    tipping_point_hours: float
    threshold_tomorrow: float
    q4_score: int
    q8_score: int
    shap_root_causes: list[str] = Field(default_factory=list)


class MicroSurveyRequest(BaseModel):
    uid: str
    email: str | None = None
    name: str | None = "Học sinh"
    current_hours: float
    mood_status: str
    trigger_reason: str = "threshold"
    top_apps: list[str] = Field(default_factory=list)
    fcm_token: str | None = None


class MicroSurveyResponse(BaseModel):
    evaluated: bool
    predicted_level: int
    result: str
    trigger_focus_mode: bool
    activate_shield: bool
    ai_alert_message: str
    shap_root_causes: list[str] = Field(default_factory=list)
    has_prior_survey: bool


class BRAMTechnicalMetadata(BaseModel):
    """Nhóm A: Thông tin kỹ thuật BRAM dành cho hệ thống và nhóm nghiên cứu."""
    D: int
    C: int
    E: int
    P: int
    S: int
    rejection_value: int
    status: str  # "ACCEPT" hoặc "ABSTAIN"
    failed_conditions: list[str] = Field(default_factory=list)
    rejection_codes: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    recommendation_codes: list[str] = Field(default_factory=list)
    scientific_sources: list[str] = Field(default_factory=list)
    human_support_required: bool = False


class BRAMStudentView(BaseModel):
    """Nhóm B: Nội dung sư phạm hiển thị cho học sinh."""
    objective_observation: str = ""
    result_or_abstention_explanation: str = ""
    educational_recommendation: str = ""
    practical_goal: str = ""
    encouragement: str = ""
    system_disclaimer: str = ""


class GeminiAdviceRequest(BaseModel):
    uid: str | None = None
    user_code: str | None = None
    name: str
    gender: str
    grade: str
    hours: float
    result_level: str
    survey_data: dict | None = None


class GeminiAdviceResponse(BaseModel):
    behavior_observation: str = ""
    screening_explanation: str = ""
    personalized_recommendations: str | list[str] = ""
    practical_goal: str = ""
    encouragement_message: str = ""
    scientific_references: list[str] = Field(default_factory=list)
    web_sources: list[dict[str, str]] = Field(default_factory=list)
    disclaimer: str = ""
    bram_technical: BRAMTechnicalMetadata | None = None


class SaveTrainingRequest(BaseModel):
    uid: str | None = None
    user_code: str | None = None
    email: str | None = None
    rating: int
    feedback_text: str | None = None
    survey_data: dict
    pred_class: int
    total_score: int
    advice_data: dict | None = None


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatContext(BaseModel):
    result_level: str | None = None
    predicted_level: int | None = None
    hours: float | None = None
    total_score: int | None = None
    symptoms: list[str] | None = None
    sas_answers: dict[str, int] | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    context: ChatContext | None = None


class ChatResponse(BaseModel):
    reply: str
    bram_technical: BRAMTechnicalMetadata
    student_display: BRAMStudentView