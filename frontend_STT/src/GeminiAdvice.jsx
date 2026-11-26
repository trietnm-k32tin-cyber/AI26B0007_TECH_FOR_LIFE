import React, { useState, useEffect } from 'react';
import Chatbot from './Chatbot';

const DEFAULT_DISCLAIMER =
  'Kết quả của hệ thống chỉ mang tính sàng lọc và hỗ trợ giáo dục thói quen sử dụng điện thoại lành mạnh, không phải kết luận chẩn đoán y khoa hay điều trị tâm lý. Nếu em gặp khó khăn kéo dài, hãy trao đổi thêm với gia đình, thầy cô hoặc chuyên viên tư vấn học đường nhé.';

const renderFormattedText = (text) => {
  if (typeof text !== 'string') return text;
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*\n]+\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={idx}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={idx}>{part.slice(1, -1)}</em>;
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
};

const toParagraphs = (value) => {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value
      .flatMap((item) => {
        if (typeof item === 'string') return item.split(/\n+/);
        if (item && typeof item === 'object') {
          const text = `${item.code ? `[${item.code}] ` : ''}${
            item.content || item.text || ''
          }`;
          return text.split(/\n+/);
        }
        return [];
      })
      .map((p) => p.trim())
      .filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(/\n+/)
      .map((p) => p.trim())
      .filter(Boolean);
  }
  return [];
};

const getSourceBadge = (src) => {
  if (src?.source) return src.source;
  try {
    const host = new URL(src.url).hostname.replace(/^www\./, '');
    if (host.includes('vertexaisearch') || host.includes('googleusercontent')) {
      return 'Hội đồng uy tín';
    }
    return host;
  } catch {
    return 'Hội đồng uy tín';
  }
};

function GeminiAdvice({
  initialAdvice,
  userInfo,
  resultLevel,
  predictedLevel,
  surveyAnswers,
  onBack,
  userCode,
  userEmail
}) {
  const [advice, setAdvice] = useState(initialAdvice || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [selectedStars, setSelectedStars] = useState(0);
  const [hoverStars, setHoverStars] = useState(0);
  const [feedbackText, setFeedbackText] = useState('');
  const [hasSubmittedFeedback, setHasSubmittedFeedback] = useState(false);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  useEffect(() => {
    if (initialAdvice) {
      setAdvice(initialAdvice);
    }
  }, [initialAdvice]);

  useEffect(() => {
    if (!advice && userInfo && userInfo.name) {
      fetchGeminiAdvice();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchGeminiAdvice = async () => {
    setLoading(true);
    setError('');
    try {
      const totalScore = Object.values(surveyAnswers || {}).reduce(
        (a, b) => a + (Number(b) || 0),
        0
      );
      const res = await fetch('/api/gemini-advice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uid: userCode || null,
          user_code: userCode || null,
          name: userInfo?.name || 'Học sinh',
          gender: userInfo?.gender || 'Nam',
          grade: userInfo?.grade || '11',
          hours: parseFloat(userInfo?.hours) || 0,
          result_level: resultLevel || 'Chưa có',
          survey_data: {
            Tong: totalScore,
            ...(surveyAnswers || {})
          }
        })
      });

      if (!res.ok) {
        throw new Error('Không thể kết nối với trợ lý hỗ trợ giáo dục lúc này.');
      }

      const data = await res.json();
      setAdvice(data);
    } catch (err) {
      console.error(err);
      setError('Có lỗi xảy ra khi tải nội dung hỗ trợ. Em vui lòng thử lại nhé!');
    } finally {
      setLoading(false);
    }
  };

  const handleRatingSubmit = async (stars) => {
    if (hasSubmittedFeedback) return;

    setSelectedStars(stars);
    setSubmittingFeedback(true);

    const levelStr = resultLevel || '';
    const predClass =
      levelStr.includes('Cao') || levelStr.includes('Nghiện')
        ? 2
        : levelStr.includes('Trung bình') || levelStr.includes('Vừa')
        ? 1
        : 0;

    const payload = {
      uid: userCode || null,
      user_code: userCode || null,
      email: userEmail || null,
      rating: stars,
      feedback_text: feedbackText.trim() || null,
      survey_data: {
        name: userInfo?.name,
        school: userInfo?.school,
        grade: userInfo?.grade,
        gender: userInfo?.gender,
        hours: parseFloat(userInfo?.hours) || 0,
        ...surveyAnswers
      },
      pred_class: predClass,
      total_score: Object.values(surveyAnswers || {}).reduce(
        (a, b) => a + (Number(b) || 0),
        0
      ),
      advice_data: advice
    };

    try {
      await fetch('/api/save-training', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      setHasSubmittedFeedback(true);
    } catch (e) {
      console.error('Lỗi gửi phản hồi:', e);
    } finally {
      setSubmittingFeedback(false);
    }
  };

  const behaviorParagraphs = toParagraphs(
    advice?.behavior_observation || advice?.analysis
  );
  const screeningParagraphs = toParagraphs(advice?.screening_explanation);
  const fallbackFactors =
    screeningParagraphs.length === 0 ? advice?.shap_root_causes || [] : [];
  const recommendationParagraphs = toParagraphs(
    advice?.personalized_recommendations || advice?.solutions
  );
  const goalParagraphs = toParagraphs(advice?.practical_goal);
  const encouragementParagraphs = toParagraphs(
    advice?.encouragement_message || advice?.parent_message
  );

  const rawReferences =
    advice?.scientific_references || advice?.medical_references || [];
  const scientificReferences = Array.isArray(rawReferences)
    ? rawReferences
    : toParagraphs(rawReferences);

  const webSources = Array.isArray(advice?.web_sources)
    ? advice.web_sources.filter((src) => src && src.url)
    : [];

  const hasAnySection =
    behaviorParagraphs.length > 0 ||
    screeningParagraphs.length > 0 ||
    fallbackFactors.length > 0 ||
    recommendationParagraphs.length > 0 ||
    goalParagraphs.length > 0 ||
    encouragementParagraphs.length > 0;

  const disclaimerText = advice?.disclaimer || DEFAULT_DISCLAIMER;
  const activeStars = hoverStars || selectedStars;

  return (
    <div
      className="advice-container"
      style={{
        position: 'relative',
        width: '100%',
        maxWidth: '850px',
        margin: '0 auto',
        background: 'transparent',
        boxShadow: 'none'
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '12px'
        }}
      >
        <button className="back-button" onClick={onBack}>
          ← Quay lại
        </button>

        {!loading && (
          <button
            className="back-button"
            onClick={fetchGeminiAdvice}
            title="Tạo lại bài chia sẻ mới"
          >
            🔄 Viết lại góc nhìn mới
          </button>
        )}
      </div>

      <h2
        style={{
          textAlign: 'center',
          marginTop: '8px',
          color: 'var(--text-main)',
          fontSize: '1.8rem',
          fontWeight: '800'
        }}
      >
        Góc Đồng Hành Thói Quen Số Dành Cho {userInfo?.name || 'Em'}
      </h2>

      {loading && (
        <div className="ai-loading-card text-center card" style={{ marginTop: '20px' }}>
          <div className="magic-spinner" style={{ fontSize: '3rem' }}>🌱</div>
          <p style={{ marginTop: '15px', fontWeight: 'bold' }}>
            T&amp;Check đang tra cứu kho tri thức và các tổ chức uy tín để viết bài chia sẻ riêng cho em...
          </p>
        </div>
      )}

      {error && (
        <div className="error-message text-center card" style={{ marginTop: '20px' }}>
          <p style={{ color: '#e53e3e', fontWeight: 'bold', fontSize: '1.1rem' }}>
            ❌ {error}
          </p>
          <button
            className="btn-primary"
            onClick={fetchGeminiAdvice}
            style={{ maxWidth: '200px', margin: '15px auto 0' }}
          >
            Thử lại 🔄
          </button>
        </div>
      )}

      {advice && !loading && (
        <div className="gemini-advice-container fade-in-up" style={{ marginTop: '20px' }}>
          <div
            className="ai-result-card-premium card"
            style={{ padding: 0, overflow: 'hidden' }}
          >
            <div className="ai-header-gradient panel-header-gradient">
              <h4>🌱 Trợ Lý Giáo Dục Học Đường T&amp;Check</h4>
              <span className="tech-badge">Kho Tri Thức &amp; Hội Đồng Uy Tín</span>
            </div>

            <div className="ai-body-content panel-scrollable-body">
              <div
                className="advice-box"
                style={{
                  background: 'rgba(245, 158, 11, 0.1)',
                  borderColor: 'rgba(245, 158, 11, 0.4)',
                  marginBottom: '24px'
                }}
              >
                <p style={{ margin: 0, fontSize: '0.92rem', lineHeight: '1.65' }}>
                  ℹ️ <strong>Lưu ý giới hạn:</strong> {disclaimerText}
                </p>
              </div>

              {!hasAnySection && (
                <div
                  className="advice-box"
                  style={{
                    background: 'rgba(239, 68, 68, 0.08)',
                    borderColor: 'rgba(239, 68, 68, 0.35)',
                    marginBottom: '24px',
                    textAlign: 'center'
                  }}
                >
                  <p style={{ margin: '0 0 12px 0', fontWeight: 600 }}>
                    ⚠️ Máy chủ vừa trả về dữ liệu trống. Hãy chắc chắn bạn đã khởi động lại server Python rồi bấm nút bên dưới.
                  </p>
                  <button
                    className="btn-primary"
                    onClick={fetchGeminiAdvice}
                    style={{ maxWidth: '240px', margin: '0 auto' }}
                  >
                    Tải lại lời khuyên 🔄
                  </button>
                </div>
              )}

              {/* Phần 1 */}
              {behaviorParagraphs.length > 0 && (
                <div className="ai-dashboard-section">
                  <h5>🔍 Phần 1. Nhận Xét Khách Quan Về Hành Vi Sử Dụng Điện Thoại</h5>
                  {behaviorParagraphs.map((para, idx) => (
                    <p
                      key={idx}
                      className="ai-text-para"
                      style={{
                        lineHeight: '1.8',
                        marginBottom: idx === behaviorParagraphs.length - 1 ? 0 : '14px'
                      }}
                    >
                      {renderFormattedText(para)}
                    </p>
                  ))}
                </div>
              )}

              {/* Phần 2 */}
              {(screeningParagraphs.length > 0 || fallbackFactors.length > 0) && (
                <div className="ai-dashboard-section">
                  <h5>🧩 Phần 2. Giải Thích Nhẹ Nhàng Về Kết Quả Sàng Lọc</h5>
                  {screeningParagraphs.length > 0 ? (
                    screeningParagraphs.map((para, idx) => (
                      <p
                        key={idx}
                        className="ai-text-para"
                        style={{
                          lineHeight: '1.8',
                          marginBottom: idx === screeningParagraphs.length - 1 ? 0 : '14px'
                        }}
                      >
                        {renderFormattedText(para)}
                      </p>
                    ))
                  ) : (
                    <ul className="premium-ai-list">
                      {fallbackFactors.map((item, idx) => (
                        <li key={idx}>
                          <span className="list-star-icon">•</span>
                          <p>{renderFormattedText(item)}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* Phần 3 */}
              {recommendationParagraphs.length > 0 && (
                <div className="ai-dashboard-section">
                  <h5>📘 Phần 3. Khuyến Nghị Cá Nhân Hóa Từ Kho Tri Thức</h5>
                  <div
                    className="advice-box"
                    style={{
                      background: 'rgba(99, 102, 241, 0.06)',
                      borderColor: 'rgba(99, 102, 241, 0.25)'
                    }}
                  >
                    {recommendationParagraphs.map((para, idx) => (
                      <p
                        key={idx}
                        className="ai-text-para"
                        style={{
                          lineHeight: '1.8',
                          marginTop: 0,
                          marginBottom:
                            idx === recommendationParagraphs.length - 1 ? 0 : '14px'
                        }}
                      >
                        {renderFormattedText(para)}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {/* Phần 4 */}
              {goalParagraphs.length > 0 && (
                <div className="ai-dashboard-section">
                  <h5>🎯 Phần 4. Mục Tiêu Thực Hành Phù Hợp Cho {userInfo?.name || 'Em'}</h5>
                  <div
                    className="advice-box"
                    style={{
                      background: 'rgba(16, 185, 129, 0.08)',
                      borderColor: 'rgba(16, 185, 129, 0.35)'
                    }}
                  >
                    {goalParagraphs.map((para, idx) => (
                      <p
                        key={idx}
                        style={{
                          marginTop: 0,
                          marginBottom: idx === goalParagraphs.length - 1 ? 0 : '12px',
                          lineHeight: '1.8'
                        }}
                      >
                        {renderFormattedText(para)}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {/* Phần 5 */}
              {encouragementParagraphs.length > 0 && (
                <div className="ai-dashboard-section">
                  <h5>💛 Phần 5. Lời Động Viên Tích Cực</h5>
                  <div className="premium-quote-box">
                    <span className="quote-icon-mark">“</span>
                    <div>
                      {encouragementParagraphs.map((para, idx) => (
                        <p
                          key={idx}
                          style={{
                            lineHeight: '1.8',
                            marginTop: 0,
                            marginBottom:
                              idx === encouragementParagraphs.length - 1 ? 0 : '12px'
                          }}
                        >
                          {renderFormattedText(para)}
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Trò chuyện kèm bối cảnh khảo sát */}
              <Chatbot
                resultLevel={resultLevel}
                predictedLevel={predictedLevel}
                surveyAnswers={surveyAnswers}
                userInfo={userInfo}
              />

              {/* Phản hồi mức độ hữu ích */}
              <div
                className="feedback-loop-section"
                style={{
                  marginTop: '30px',
                  padding: '20px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  borderRadius: '16px',
                  border: '1px solid rgba(150, 150, 150, 0.2)',
                  textAlign: 'center'
                }}
              >
                <h5
                  style={{
                    color: 'var(--primary)',
                    marginBottom: '8px',
                    fontSize: '1.1rem'
                  }}
                >
                  🌟 Đánh Giá Mức Độ Hữu Ích
                </h5>
                <p
                  style={{
                    fontSize: '0.9rem',
                    color: 'var(--text-muted)',
                    marginBottom: '15px'
                  }}
                >
                  Nội dung hỗ trợ này có dễ hiểu và phù hợp với em không? Góp ý của em giúp hệ thống hoàn thiện tốt hơn.
                </p>

                {!hasSubmittedFeedback && (
                  <div style={{ marginBottom: '15px' }}>
                    <input
                      type="text"
                      value={feedbackText}
                      onChange={(e) => setFeedbackText(e.target.value)}
                      placeholder="Viết nhận xét hoặc góp ý ngắn (không bắt buộc)..."
                      style={{
                        width: '100%',
                        maxWidth: '450px',
                        padding: '10px 16px',
                        borderRadius: '10px',
                        border: '1px solid rgba(150,150,150,0.3)',
                        outline: 'none',
                        fontSize: '0.9rem',
                        background: 'rgba(255,255,255,0.8)',
                        color: '#000'
                      }}
                    />
                  </div>
                )}

                <div
                  style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}
                  onMouseLeave={() => setHoverStars(0)}
                >
                  {[1, 2, 3, 4, 5].map((num) => (
                    <span
                      key={num}
                      style={{
                        fontSize: '2.2rem',
                        cursor: hasSubmittedFeedback ? 'default' : 'pointer',
                        color: activeStars >= num ? '#fbbf24' : '#6b7280',
                        transition: 'transform 0.2s, color 0.2s',
                        transform: activeStars >= num ? 'scale(1.15)' : 'scale(1)'
                      }}
                      onMouseEnter={() => !hasSubmittedFeedback && setHoverStars(num)}
                      onClick={() => handleRatingSubmit(num)}
                    >
                      ★
                    </span>
                  ))}
                </div>

                {submittingFeedback && (
                  <p
                    style={{
                      fontSize: '0.85rem',
                      color: 'var(--primary)',
                      marginTop: '8px'
                    }}
                  >
                    ⏳ Đang ghi nhận phản hồi...
                  </p>
                )}
                {hasSubmittedFeedback && (
                  <p
                    style={{
                      color: '#10b981',
                      fontWeight: 'bold',
                      marginTop: '10px',
                      fontSize: '0.95rem'
                    }}
                  >
                    ✅ Cảm ơn em! Phản hồi của em đã được hệ thống ghi nhận.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default GeminiAdvice;