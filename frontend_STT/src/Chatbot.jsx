import React, { useState, useRef, useEffect } from 'react';

const SAS_SV_SHORT_LABELS = {
  Q1: 'Bỏ lỡ kế hoạch vì điện thoại',
  Q2: 'Khó tập trung học tập',
  Q3: 'Đau mỏi cổ tay hoặc sau gáy',
  Q4: 'Khó chịu khi không có điện thoại',
  Q5: 'Thiếu kiên nhẫn khi xa điện thoại',
  Q6: 'Luôn nghĩ đến điện thoại',
  Q7: 'Khó giảm dùng dù ảnh hưởng sinh hoạt',
  Q8: 'Kiểm tra mạng xã hội thường xuyên',
  Q9: 'Dùng lâu hơn dự định',
  Q10: 'Người xung quanh nhắc nhở về thời gian dùng'
};

function Chatbot({ userInfo, resultLevel, predictedLevel, surveyAnswers }) {
  const [history, setHistory] = useState([
    {
      role: 'model',
      text: 'Chào em! Mình là trợ lý AI hỗ trợ giáo dục học đường của T&Check. Mình không phải bác sĩ hay chuyên viên tâm lý, nhưng có thể cùng em trao đổi và gợi ý những cách nhẹ nhàng để xây dựng thói quen dùng điện thoại cân bằng hơn. Em đang băn khoăn điều gì không?',
      bramTechnical: null,
      studentDisplay: null
    }
  ]);
  const [inputMsg, setInputMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showResearcherPanel, setShowResearcherPanel] = useState(false);
  const chatWindowRef = useRef(null);

  useEffect(() => {
    if (chatWindowRef.current) {
      chatWindowRef.current.scrollTop = chatWindowRef.current.scrollHeight;
    }
  }, [history]);

  const buildContext = () => {
    const highlightedBehaviors = Object.entries(surveyAnswers || {})
      .filter(([key, val]) => SAS_SV_SHORT_LABELS[key] && Number(val) >= 4)
      .map(([key]) => SAS_SV_SHORT_LABELS[key]);

    const cleanAnswers = {};
    for (let i = 1; i <= 10; i += 1) {
      const key = `Q${i}`;
      if (surveyAnswers && surveyAnswers[key] !== undefined) {
        cleanAnswers[key] = Number(surveyAnswers[key]);
      }
    }

    const totalScore = Object.values(cleanAnswers).reduce((a, b) => a + b, 0);

    return {
      result_level: resultLevel || '',
      predicted_level: predictedLevel !== undefined ? predictedLevel : null,
      hours: userInfo?.hours !== undefined ? parseFloat(userInfo.hours) : null,
      total_score: Object.keys(cleanAnswers).length > 0 ? totalScore : null,
      symptoms: highlightedBehaviors,
      sas_answers: Object.keys(cleanAnswers).length > 0 ? cleanAnswers : null
    };
  };

  const handleSend = async () => {
    if (!inputMsg.trim() || isLoading) return;

    const userMessage = inputMsg.trim();
    const currentHistory = [...history];
    setHistory([
      ...currentHistory,
      { role: 'user', text: userMessage, bramTechnical: null, studentDisplay: null }
    ]);
    setInputMsg('');
    setIsLoading(true);

    try {
      const res = await fetch('/api/gemini-chat-bram', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          history: currentHistory.slice(1).map((m) => ({ role: m.role, text: m.text })),
          message: userMessage,
          context: buildContext()
        })
      });

      if (!res.ok) throw new Error('Lỗi kết nối API');
      const data = await res.json();

      setHistory((prev) => [
        ...prev,
        {
          role: 'model',
          text: data.reply,
          bramTechnical: data.bram_technical || null,
          studentDisplay: data.student_display || null
        }
      ]);
    } catch (error) {
      setHistory((prev) => [
        ...prev,
        {
          role: 'model',
          text: 'Hiện tại hệ thống đang gián đoạn kết nối. Em vui lòng nhắn lại sau ít phút nhé!',
          bramTechnical: null,
          studentDisplay: null
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chatbot-container ai-dashboard-section">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '10px',
          flexWrap: 'wrap',
          marginBottom: '10px'
        }}
      >
        <h5 style={{ margin: 0 }}>💬 Trò chuyện cùng Trợ lý Giáo dục Học đường T&amp;Check</h5>
        <button
          type="button"
          onClick={() => setShowResearcherPanel((prev) => !prev)}
          style={{
            fontSize: '0.78rem',
            padding: '5px 11px',
            borderRadius: '999px',
            border: '1px solid rgba(99, 102, 241, 0.35)',
            background: showResearcherPanel ? 'rgba(99, 102, 241, 0.16)' : 'transparent',
            color: 'var(--text-main)',
            cursor: 'pointer',
            fontWeight: '600'
          }}
          title="Hiển thị hoặc ẩn thông số kỹ thuật BRAM dành cho nhóm nghiên cứu"
        >
          {showResearcherPanel ? '🔬 Ẩn thông số BRAM (Nhóm A)' : '🔬 Xem kiểm soát BRAM (Nhóm A)'}
        </button>
      </div>

      <div className="chat-window" ref={chatWindowRef}>
        {history.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.role}`}>
            {/* NHÓM B: NỘI DUNG SƯ PHẠM HIỂN THỊ CHO HỌC SINH */}
            <div className="msg-bubble" style={{ whiteSpace: 'pre-line' }}>
              {msg.text}

              {msg.role === 'model' && msg.studentDisplay?.practical_goal && (
                <div
                  style={{
                    marginTop: '10px',
                    padding: '8px 12px',
                    borderRadius: '10px',
                    background: 'rgba(16, 185, 129, 0.12)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    fontSize: '0.85rem'
                  }}
                >
                  🎯 <strong>Mục tiêu nhỏ gợi ý:</strong> {msg.studentDisplay.practical_goal}
                </div>
              )}
            </div>

            {/* NHÓM A: THÔNG SỐ KỸ THUẬT BRAM DÀNH CHO NHÓM NGHIÊN CỨU */}
            {showResearcherPanel && msg.role === 'model' && msg.bramTechnical && (
              <div
                style={{
                  marginTop: '6px',
                  padding: '10px 12px',
                  borderRadius: '10px',
                  background: 'rgba(15, 23, 42, 0.06)',
                  border: '1px dashed rgba(99, 102, 241, 0.4)',
                  fontSize: '0.78rem',
                  lineHeight: '1.55',
                  color: 'var(--text-main)'
                }}
              >
                <div style={{ fontWeight: '700', marginBottom: '4px' }}>
                  📊 Nhóm A — Kiểm soát BRAM (R = 1 − D×C×E×P×S):{' '}
                  <span
                    style={{
                      color: msg.bramTechnical.status === 'ACCEPT' ? '#10b981' : '#f59e0b'
                    }}
                  >
                    {msg.bramTechnical.status} (R = {msg.bramTechnical.rejection_value})
                  </span>
                </div>
                <div>
                  • Giá trị điều kiện: <strong>D={msg.bramTechnical.D}</strong> |{' '}
                  <strong>C={msg.bramTechnical.C}</strong> |{' '}
                  <strong>E={msg.bramTechnical.E}</strong> |{' '}
                  <strong>P={msg.bramTechnical.P}</strong> |{' '}
                  <strong>S={msg.bramTechnical.S}</strong>
                </div>
                <div>
                  • Điều kiện không đạt:{' '}
                  {msg.bramTechnical.failed_conditions?.length > 0
                    ? msg.bramTechnical.failed_conditions.join(', ')
                    : 'Không có'}
                  {msg.bramTechnical.rejection_codes?.length > 0 &&
                    ` (${msg.bramTechnical.rejection_codes.join(', ')})`}
                </div>
                {msg.bramTechnical.rejection_reasons?.length > 0 && (
                  <div>• Lý do từ chối: {msg.bramTechnical.rejection_reasons.join(' | ')}</div>
                )}
                <div>
                  • Tài liệu kho tri thức:{' '}
                  {msg.bramTechnical.scientific_sources?.length > 0
                    ? msg.bramTechnical.scientific_sources.join('; ')
                    : 'Không có trích xuất trực tiếp'}
                </div>
                <div>
                  • Yêu cầu hỗ trợ con người:{' '}
                  <strong>{msg.bramTechnical.human_support_required ? 'Có' : 'Không'}</strong>
                </div>
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="chat-message model">
            <div className="msg-bubble loading-dots">Trợ lý đang đối chiếu kho tri thức &amp; kiểm duyệt BRAM...</div>
          </div>
        )}
      </div>

      <div className="chat-input-area">
        <input
          type="text"
          value={inputMsg}
          onChange={(e) => setInputMsg(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Nhập điều em muốn trao đổi về thói quen dùng điện thoại..."
          disabled={isLoading}
        />
        <button onClick={handleSend} disabled={isLoading || !inputMsg.trim()}>
          Gửi 🚀
        </button>
      </div>

      <p
        style={{
          fontSize: '0.8rem',
          color: 'var(--text-muted)',
          marginTop: '8px',
          textAlign: 'center'
        }}
      >
        Trợ lý AI chỉ hỗ trợ giáo dục thói quen sử dụng điện thoại lành mạnh, không thay thế chẩn đoán y khoa hay tư vấn tâm lý chuyên sâu.
      </p>
    </div>
  );
}

export default Chatbot;