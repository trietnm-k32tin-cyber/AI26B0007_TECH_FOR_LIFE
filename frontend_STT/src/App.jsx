import React, { useState, useEffect } from 'react';
import GeminiAdvice from './GeminiAdvice';
import './App.css';

const QUESTIONS = [
  'Bỏ lỡ công việc theo kế hoạch do sử dụng điện thoại thông minh.',
  'Khó tập trung trong lớp, trong khi làm bài tập hoặc trong khi làm việc do sử dụng điện thoại thông minh.',
  'Cảm thấy đau nhức ở cổ tay hoặc sau gáy trong khi sử dụng điện thoại thông minh.',
  'Sẽ không chịu đựng được nếu không có điện thoại thông minh.',
  'Cảm thấy thiếu kiên nhẫn và bực bội khi không có điện thoại thông minh.',
  'Có điện thoại thông minh trong tâm trí ngay cả khi bạn không sử dụng nó.',
  'Bạn sẽ không bao giờ từ bỏ việc sử dụng điện thoại thông minh của mình ngay cả khi cuộc sống hàng ngày của bạn đã bị ảnh hưởng rất nhiều bởi nó.',
  'Thường xuyên kiểm tra điện thoại thông minh để không bỏ lỡ những cuộc trò chuyện hay thông tin trên mạng xã hội.',
  'Sử dụng điện thoại thông minh lâu hơn dự định.',
  'Những người xung quanh (gia đình, bạn bè) phàn nàn về việc bạn dành quá nhiều thời gian cho điện thoại thông minh.'
];

const STORAGE_KEY = 'tcheck_supabase_user';

function App() {
  const [theme, setTheme] = useState('light');
  const [step, setStep] = useState(0);

  // Trạng thái tài khoản Supabase & Giao diện Đăng nhập / Đăng ký
  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authTab, setAuthTab] = useState('login'); // 'login' | 'register'
  const [authForm, setAuthForm] = useState({
    username: '',
    password: '',
    confirmPassword: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [authError, setAuthError] = useState('');
  const [authSuccess, setAuthSuccess] = useState('');

  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [sessionHistory, setSessionHistory] = useState([]);

  const [userInfo, setUserInfo] = useState({
    name: '',
    school: '',
    grade: '11',
    gender: 'Nam',
    hours: 4
  });

  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(false);
  const [resultData, setResultData] = useState(null);
  const [userCount, setUserCount] = useState(0);
  const [hasRated, setHasRated] = useState(false);
  const [selectedStars, setSelectedStars] = useState(0);

  const [geminiAdvice, setGeminiAdvice] = useState(null);
  const [geminiLoading, setGeminiLoading] = useState(false);
  const [geminiError, setGeminiError] = useState('');

  const parseSafeJson = async (res) => {
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch (err) {
      throw new Error(`Máy chủ gặp phản hồi lỗi (${res.status}): ${text.substring(0, 100)}`);
    }
  };

  // Tải hồ sơ và lịch sử khảo sát của người dùng từ Supabase
  const loadUserDataFromSupabase = async (userCode) => {
    if (!userCode) return;
    try {
      const res = await fetch(`/api/users/${encodeURIComponent(userCode)}/profile`);
      if (!res.ok) return;
      const data = await parseSafeJson(res);
      if (data.user_info) {
        setCurrentUser(data.user_info);
        setUserInfo((prev) => ({
          ...prev,
          name: data.user_info.name || prev.name,
          school: data.user_info.school || prev.school,
          grade: data.user_info.grade || prev.grade,
          gender: data.user_info.gender || prev.gender
        }));
      }
      if (Array.isArray(data.session_history)) {
        setSessionHistory(data.session_history);
      }
    } catch (err) {
      console.error('Lỗi tải dữ liệu từ Supabase:', err);
    }
  };

  // Khôi phục phiên đăng nhập khi tải lại trang
  useEffect(() => {
    const initSession = async () => {
      try {
        const raw =
          localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY);
        if (raw) {
          const savedUser = JSON.parse(raw);
          setCurrentUser(savedUser);
          setUserInfo((prev) => ({
            ...prev,
            name: savedUser.name || '',
            school: savedUser.school || '',
            grade: savedUser.grade || '11',
            gender: savedUser.gender || 'Nam'
          }));
          await loadUserDataFromSupabase(savedUser.user_code);
        }
      } catch (err) {
        console.error('Lỗi khôi phục phiên đăng nhập:', err);
      } finally {
        setAuthLoading(false);
      }
    };
    initSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Đồng bộ hồ sơ học sinh sang bảng users trên Supabase
  const syncUserToSupabase = async (user, profile = {}) => {
    if (!user?.user_code) return;
    try {
      await fetch('/api/users/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uid: user.user_code,
          user_code: user.user_code,
          email: user.email || null,
          name: profile.name || user.name || '',
          school: profile.school || null,
          grade: profile.grade || null,
          gender: profile.gender || null
        })
      });
    } catch (err) {
      console.error('Lỗi đồng bộ tài khoản lên Supabase:', err);
    }
  };

  // Đánh giá độ mạnh mật khẩu cho màn hình Đăng ký
  const getPasswordStrength = (pwd) => {
    if (!pwd) return { score: 0, label: '', color: '#cbd5e1' };
    let score = 0;
    if (pwd.length >= 6) score += 1;
    if (pwd.length >= 8) score += 1;
    if (/[A-Za-z]/.test(pwd) && /[0-9]/.test(pwd)) score += 1;
    if (/[^A-Za-z0-9]/.test(pwd)) score += 1;

    if (score <= 1) return { score: 1, label: 'Yếu', color: '#ef4444' };
    if (score <= 2) return { score: 2, label: 'Trung bình', color: '#f59e0b' };
    return { score: 3, label: 'Mạnh', color: '#10b981' };
  };

  const switchAuthTab = (tab) => {
    setAuthTab(tab);
    setAuthError('');
    setAuthSuccess('');
    setAuthForm((prev) => ({ ...prev, password: '', confirmPassword: '' }));
  };

  const handleAuthInputChange = (e) => {
    const { name, value } = e.target;
    setAuthError('');
    setAuthSuccess('');
    setAuthForm((prev) => ({ ...prev, [name]: value }));
  };

  const persistUserSession = (userObj, remember) => {
    const serialized = JSON.stringify(userObj);
    if (remember) {
      localStorage.setItem(STORAGE_KEY, serialized);
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, serialized);
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  // Xử lý Đăng nhập
  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setAuthError('');
    setAuthSuccess('');

    if (!authForm.username.trim() || !authForm.password) {
      setAuthError('Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.');
      return;
    }

    try {
      setLoading(true);
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: authForm.username.trim(),
          password: authForm.password
        })
      });
      const data = await parseSafeJson(res);
      if (!res.ok) {
        throw new Error(data.detail || 'Đăng nhập thất bại.');
      }

      const loggedUser = data.user_info;
      setCurrentUser(loggedUser);
      setSessionHistory(data.session_history || []);
      setUserInfo((prev) => ({
        ...prev,
        name: loggedUser.name || '',
        school: loggedUser.school || '',
        grade: loggedUser.grade || '11',
        gender: loggedUser.gender || 'Nam'
      }));
      persistUserSession(loggedUser, rememberMe);
    } catch (err) {
      setAuthError(err.message || 'Không thể đăng nhập lúc này.');
    } finally {
      setLoading(false);
    }
  };

  // Xử lý Đăng ký
  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    setAuthError('');
    setAuthSuccess('');

    const cleanUsername = authForm.username.trim();
    if (!cleanUsername || !authForm.password || !authForm.confirmPassword) {
      setAuthError('Vui lòng điền đầy đủ thông tin đăng ký.');
      return;
    }
    if (!/^[a-zA-Z0-9_.]{3,30}$/.test(cleanUsername)) {
      setAuthError(
        'Tên đăng nhập từ 3–30 ký tự, chỉ gồm chữ không dấu, số, dấu chấm (.) hoặc gạch dưới (_).'
      );
      return;
    }
    if (authForm.password.length < 6) {
      setAuthError('Mật khẩu phải có ít nhất 6 ký tự.');
      return;
    }
    if (authForm.password !== authForm.confirmPassword) {
      setAuthError('Mật khẩu xác nhận không khớp.');
      return;
    }

    try {
      setLoading(true);
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: cleanUsername,
          password: authForm.password
        })
      });
      const data = await parseSafeJson(res);
      if (!res.ok) {
        throw new Error(data.detail || 'Đăng ký thất bại.');
      }

      const newUser = data.user_info;
      setCurrentUser(newUser);
      setSessionHistory([]);
      setUserInfo((prev) => ({
        ...prev,
        name: newUser.name || '',
        school: newUser.school || '',
        grade: newUser.grade || '11',
        gender: newUser.gender || 'Nam'
      }));
      persistUserSession(newUser, true);
    } catch (err) {
      setAuthError(err.message || 'Không thể tạo tài khoản lúc này.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
    setCurrentUser(null);
    setSessionHistory([]);
    setShowUserMenu(false);
    setShowHistoryDrawer(false);
    setResultData(null);
    setGeminiAdvice(null);
    setAnswers({});
    setAuthForm({ username: '', password: '', confirmPassword: '' });
    setAuthError('');
    setAuthSuccess('');
    setStep(0);
  };

  const handleStartSurveyAfterProfile = async () => {
    if (!userInfo.name.trim() || !userInfo.school.trim()) {
      return alert('Vui lòng nhập đầy đủ Họ tên và Trường học!');
    }
    if (currentUser) {
      const updatedUser = {
        ...currentUser,
        name: userInfo.name.trim(),
        school: userInfo.school.trim(),
        grade: userInfo.grade,
        gender: userInfo.gender
      };
      setCurrentUser(updatedUser);
      if (localStorage.getItem(STORAGE_KEY)) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedUser));
      } else {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(updatedUser));
      }
      await syncUserToSupabase(updatedUser, userInfo);
    }
    setStep(1);
  };

  const fetchUserCount = async () => {
    try {
      const res = await fetch('/api/stats');
      if (res.ok) {
        const data = await res.json();
        setUserCount(data.total_users || 0);
      }
    } catch (error) {
      console.error('Lỗi lấy tổng số lượng người tham gia:', error);
    }
  };

  useEffect(() => {
    fetchUserCount();
  }, []);

  const toggleTheme = () => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));

  const handleInfoChange = (e) => {
    const { id, value } = e.target;
    setUserInfo((prev) => ({ ...prev, [id]: value }));
  };

  const handleOptionChange = (qIndex, value) => {
    setAnswers((prev) => ({ ...prev, [`Q${qIndex}`]: parseInt(value, 10) }));
  };

  const handleMainRatingSubmit = async (stars) => {
    if (hasRated) return;
    setHasRated(true);
    setSelectedStars(stars);

    try {
      await fetch('/api/save-training', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uid: currentUser?.user_code || null,
          user_code: currentUser?.user_code || null,
          email: currentUser?.email || null,
          rating: stars,
          feedback_text: null,
          survey_data: {
            name: userInfo.name,
            school: userInfo.school,
            grade: userInfo.grade,
            gender: userInfo.gender,
            hours: parseFloat(userInfo.hours) || 0,
            ...answers
          },
          pred_class: resultData.predicted_level,
          total_score: Object.values(answers).reduce((a, b) => a + b, 0),
          advice_data: null
        })
      });
    } catch (err) {
      console.error('Lỗi lưu đánh giá:', err);
    }
  };

  const nextStep = () => {
    if (step > 0 && !answers[`Q${step}`]) {
      alert('Vui lòng chọn một mức độ phù hợp với bạn!');
      return;
    }
    setStep((prev) => prev + 1);
  };

  const prevStep = () => setStep((prev) => (prev > 0 ? prev - 1 : 0));

  const submitSurvey = async () => {
    if (!answers['Q10']) {
      alert('Vui lòng chọn mức độ cho câu hỏi cuối cùng!');
      return;
    }

    setLoading(true);
    setGeminiAdvice(null);
    setHasRated(false);
    setSelectedStars(0);

    const payload = {
      uid: currentUser?.user_code || null,
      user_code: currentUser?.user_code || null,
      email: currentUser?.email || null,
      name: userInfo.name,
      tg_sudung_dt: parseFloat(userInfo.hours) || 0,
      Truong: userInfo.school,
      Khoi: userInfo.grade,
      Phai: userInfo.gender,
      ...answers
    };

    try {
      const res = await fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);

      const data = await parseSafeJson(res);
      if (data.predicted_level !== undefined) {
        setResultData(data);
        fetchUserCount();
        if (currentUser?.user_code) {
          await loadUserDataFromSupabase(currentUser.user_code);
        }
        setStep(11);
      }
    } catch (error) {
      console.error('Fetch Error:', error);
      setResultData({
        result: 'Trung bình',
        predicted_level: 1,
        advice:
          'Hiện chưa thể kết nối máy chủ để phân tích chi tiết. Em có thể thử thực hiện lại sau ít phút nhé.'
      });
      setStep(11);
    } finally {
      setLoading(false);
    }
  };

  const fetchGeminiAdvice = async () => {
    if (!hasRated) return;
    setGeminiLoading(true);
    setGeminiError('');
    try {
      const res = await fetch('/api/gemini-advice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uid: currentUser?.user_code || null,
          user_code: currentUser?.user_code || null,
          name: userInfo.name || 'Học sinh',
          gender: userInfo.gender || 'Nam',
          grade: userInfo.grade || '11',
          hours: parseFloat(userInfo.hours) || 0,
          result_level: resultData.result,
          survey_data: {
            Tong: Object.values(answers).reduce((a, b) => a + b, 0),
            ...answers
          }
        })
      });

      const data = await parseSafeJson(res);
      if (!res.ok) {
        throw new Error(
          data.detail || 'Không thể tải nội dung hỗ trợ giáo dục từ hệ thống.'
        );
      }
      setGeminiAdvice(data);
    } catch (err) {
      setGeminiError(
        err.message || 'Không thể kết nối dịch vụ hỗ trợ giáo dục lúc này.'
      );
    } finally {
      setGeminiLoading(false);
    }
  };

  const resetSurvey = () => {
    setAnswers({});
    setStep(0);
    setResultData(null);
    setGeminiAdvice(null);
    setGeminiError('');
    setHasRated(false);
    setSelectedStars(0);
  };

  const getBadgeStyle = (resultStr) => {
    const text = resultStr || '';
    if (text.includes('Cao') || text.includes('Nghiện')) {
      return {
        border: '2px solid #ef4444',
        color: '#ff6b6b',
        bg: 'rgba(239, 68, 68, 0.15)'
      };
    }
    if (text.includes('Trung bình') || text.includes('Vừa')) {
      return {
        border: '2px solid #f59e0b',
        color: '#fbbf24',
        bg: 'rgba(245, 158, 11, 0.15)'
      };
    }
    return {
      border: '2px solid #10b981',
      color: '#34d399',
      bg: 'rgba(16, 185, 129, 0.15)'
    };
  };

  const passwordStrength = getPasswordStrength(authForm.password);
  const userInitial = (
    currentUser?.name?.[0] ||
    currentUser?.username?.[0] ||
    'U'
  ).toUpperCase();

  return (
    <div className="app-container" data-theme={theme}>
      {/* THANH NAVBAR TRÊN CÙNG */}
      <nav
        style={{
          width: '100%',
          maxWidth: '1250px',
          display: 'flex',
          justifyContent: currentUser ? 'space-between' : 'flex-end',
          alignItems: 'center',
          padding: '8px 12px',
          marginBottom: '10px',
          zIndex: 20
        }}
      >
        {/* GÓC TRÁI: Tài khoản người dùng đã đăng nhập */}
        {currentUser && (
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                background: 'var(--panel-bg)',
                border: '1px solid rgba(150,150,150,0.25)',
                padding: '6px 14px',
                borderRadius: '30px',
                cursor: 'pointer',
                color: 'var(--text-main)',
                fontWeight: '600'
              }}
            >
              <span
                style={{
                  width: '30px',
                  height: '30px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  color: '#fff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: '800',
                  fontSize: '0.9rem'
                }}
              >
                {userInitial}
              </span>
              <span style={{ fontSize: '0.9rem' }}>@{currentUser.username}</span>
            </button>

            {showUserMenu && (
              <div
                style={{
                  position: 'absolute',
                  top: '48px',
                  left: 0,
                  background: 'var(--bg-app)',
                  border: '1px solid rgba(150,150,150,0.25)',
                  borderRadius: '14px',
                  padding: '14px',
                  minWidth: '235px',
                  boxShadow: 'var(--shadow)',
                  zIndex: 30
                }}
              >
                <p style={{ margin: '0 0 4px 0', fontWeight: 'bold', fontSize: '0.95rem' }}>
                  {currentUser.name || `@${currentUser.username}`}
                </p>
                <p style={{ margin: '0 0 12px 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Tài khoản: @{currentUser.username} • {currentUser.user_code}
                </p>
                <button
                  onClick={handleLogout}
                  style={{
                    width: '100%',
                    padding: '9px',
                    borderRadius: '10px',
                    border: 'none',
                    background: '#ef4444',
                    color: '#fff',
                    fontWeight: '700',
                    cursor: 'pointer'
                  }}
                >
                  🚪 Đăng xuất tài khoản
                </button>
              </div>
            )}
          </div>
        )}

        {/* GÓC PHẢI: Nút đổi theme + Lịch sử khảo sát */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={toggleTheme}
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '50%',
              border: '1px solid rgba(150,150,150,0.25)',
              background: 'var(--panel-bg)',
              cursor: 'pointer',
              fontSize: '1.1rem'
            }}
            title="Đổi giao diện Sáng / Tối"
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>

          {currentUser && (
            <button
              onClick={() => setShowHistoryDrawer(true)}
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '50%',
                border: '1px solid rgba(150,150,150,0.25)',
                background: 'var(--panel-bg)',
                cursor: 'pointer',
                fontSize: '1.3rem',
                fontWeight: 'bold',
                color: 'var(--text-main)'
              }}
              title="Lịch sử khảo sát"
            >
              ≡
            </button>
          )}
        </div>
      </nav>

      {/* NGĂN KÉO BÊN PHẢI HIỂN THỊ LỊCH SỬ THỰC HIỆN KHẢO SÁT */}
      {showHistoryDrawer && (
        <div
          onClick={() => setShowHistoryDrawer(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.45)',
            zIndex: 50,
            display: 'flex',
            justifyContent: 'flex-end'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '360px',
              maxWidth: '85vw',
              height: '100%',
              background: 'var(--bg-app)',
              color: 'var(--text-main)',
              padding: '24px',
              overflowY: 'auto',
              boxShadow: '-8px 0 30px rgba(0,0,0,0.25)'
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '18px'
              }}
            >
              <h3 style={{ margin: 0 }}>📋 Lịch sử khảo sát ({sessionHistory.length})</h3>
              <button
                onClick={() => setShowHistoryDrawer(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  fontSize: '1.3rem',
                  cursor: 'pointer',
                  color: 'var(--text-main)'
                }}
              >
                ✕
              </button>
            </div>

            {sessionHistory.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                Em chưa có lượt khảo sát nào được lưu trên tài khoản này.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {sessionHistory.map((item, idx) => (
                  <div
                    key={item.id || idx}
                    style={{
                      padding: '14px',
                      borderRadius: '14px',
                      background: 'rgba(150,150,150,0.08)',
                      border: '1px solid rgba(150,150,150,0.2)'
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        marginBottom: '6px'
                      }}
                    >
                      <strong style={{ fontSize: '0.85rem', color: 'var(--primary)' }}>
                        {String(item.date || '').slice(0, 10)}
                      </strong>
                      <span style={{ fontWeight: 'bold', fontSize: '0.85rem' }}>
                        Mức nguy cơ: {item.prediction}
                      </span>
                    </div>
                    <p style={{ margin: '4px 0', fontSize: '0.85rem' }}>
                      ⏱️ Thời gian dùng TB: <strong>{item.avgHours} giờ/ngày</strong>
                    </p>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      📊 Tổng điểm SAS-SV: {item.totalScore}/60
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <header className="header-section">
        <h1 className="title-main" style={{ fontSize: '2.2rem' }}>
          T&amp;Check — Thói Quen Số Lành Mạnh
        </h1>
        <p className="subtitle" style={{ fontSize: '1.15rem', fontWeight: '600' }}>
          HỆ THỐNG SÀNG LỌC VÀ HỖ TRỢ GIÁO DỤC THÓI QUEN DÙNG ĐIỆN THOẠI CHO HỌC SINH THPT
        </p>
      </header>

      <main className={`main-content ${geminiAdvice && step === 11 ? 'wide-layout' : ''}`}>
        {step < 11 && (
          <div className="card shadow-animated">
            {step === 0 && (
              <div className="fade-in">
                {authLoading ? (
                  <p className="text-center">Đang kiểm tra phiên đăng nhập...</p>
                ) : !currentUser ? (
                  <div style={{ maxWidth: '420px', margin: '0 auto', padding: '6px 0' }}>
                    {/* THANH CHUYỂN TAB ĐĂNG NHẬP / ĐĂNG KÝ */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '6px',
                        padding: '6px',
                        borderRadius: '14px',
                        background: 'rgba(148, 163, 184, 0.14)',
                        marginBottom: '22px'
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => switchAuthTab('login')}
                        style={{
                          padding: '11px 14px',
                          borderRadius: '10px',
                          border: 'none',
                          fontWeight: '700',
                          fontSize: '0.95rem',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          background:
                            authTab === 'login' ? 'var(--primary, #10b981)' : 'transparent',
                          color: authTab === 'login' ? '#ffffff' : 'var(--text-main)',
                          boxShadow:
                            authTab === 'login' ? '0 4px 12px rgba(16,185,129,0.28)' : 'none'
                        }}
                      >
                        Đăng nhập
                      </button>
                      <button
                        type="button"
                        onClick={() => switchAuthTab('register')}
                        style={{
                          padding: '11px 14px',
                          borderRadius: '10px',
                          border: 'none',
                          fontWeight: '700',
                          fontSize: '0.95rem',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          background:
                            authTab === 'register' ? 'var(--primary, #10b981)' : 'transparent',
                          color: authTab === 'register' ? '#ffffff' : 'var(--text-main)',
                          boxShadow:
                            authTab === 'register' ? '0 4px 12px rgba(16,185,129,0.28)' : 'none'
                        }}
                      >
                        Đăng ký
                      </button>
                    </div>

                    {authError && (
                      <div
                        style={{
                          padding: '11px 14px',
                          borderRadius: '10px',
                          background: 'rgba(239, 68, 68, 0.12)',
                          border: '1px solid rgba(239, 68, 68, 0.35)',
                          color: '#ef4444',
                          fontSize: '0.88rem',
                          fontWeight: '600',
                          marginBottom: '16px'
                        }}
                      >
                        ⚠️ {authError}
                      </div>
                    )}

                    {authSuccess && (
                      <div
                        style={{
                          padding: '11px 14px',
                          borderRadius: '10px',
                          background: 'rgba(16, 185, 129, 0.12)',
                          border: '1px solid rgba(16, 185, 129, 0.35)',
                          color: '#10b981',
                          fontSize: '0.88rem',
                          fontWeight: '600',
                          marginBottom: '16px'
                        }}
                      >
                        ✅ {authSuccess}
                      </div>
                    )}

                    {/* PHẦN 1: FORM ĐĂNG NHẬP */}
                    {authTab === 'login' ? (
                      <form onSubmit={handleLoginSubmit}>
                        <h3 className="section-title" style={{ marginBottom: '6px' }}>
                          👋 Chào mừng quay trở lại
                        </h3>
                        <p
                          style={{
                            color: 'var(--text-muted)',
                            fontSize: '0.9rem',
                            marginBottom: '20px'
                          }}
                        >
                          Đăng nhập bằng tên tài khoản để tiếp tục khảo sát và xem lịch sử.
                        </p>

                        <div className="form-group">
                          <label>Tên đăng nhập</label>
                          <input
                            type="text"
                            name="username"
                            value={authForm.username}
                            onChange={handleAuthInputChange}
                            placeholder="Nhập tên đăng nhập..."
                            autoComplete="username"
                          />
                        </div>

                        <div className="form-group">
                          <label>Mật khẩu</label>
                          <div style={{ position: 'relative' }}>
                            <input
                              type={showPassword ? 'text' : 'password'}
                              name="password"
                              value={authForm.password}
                              onChange={handleAuthInputChange}
                              placeholder="Nhập mật khẩu..."
                              autoComplete="current-password"
                              style={{ paddingRight: '44px' }}
                            />
                            <button
                              type="button"
                              onClick={() => setShowPassword(!showPassword)}
                              aria-label="Hiện hoặc ẩn mật khẩu"
                              style={{
                                position: 'absolute',
                                right: '10px',
                                top: '50%',
                                transform: 'translateY(-50%)',
                                background: 'transparent',
                                border: 'none',
                                cursor: 'pointer',
                                fontSize: '1.1rem',
                                color: 'var(--text-muted)'
                              }}
                            >
                              {showPassword ? '🙈' : '👁️'}
                            </button>
                          </div>
                        </div>

                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginBottom: '18px',
                            fontSize: '0.88rem'
                          }}
                        >
                          <label
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              cursor: 'pointer',
                              margin: 0,
                              color: 'var(--text-muted)'
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={rememberMe}
                              onChange={(e) => setRememberMe(e.target.checked)}
                              style={{ width: 'auto', margin: 0 }}
                            />
                            Ghi nhớ đăng nhập
                          </label>
                        </div>

                        <button type="submit" className="btn-primary" disabled={loading}>
                          {loading ? 'Đang đăng nhập...' : 'Đăng nhập 🚀'}
                        </button>

                        <p
                          style={{
                            textAlign: 'center',
                            marginTop: '18px',
                            fontSize: '0.9rem',
                            color: 'var(--text-muted)'
                          }}
                        >
                          Chưa có tài khoản?{' '}
                          <button
                            type="button"
                            onClick={() => switchAuthTab('register')}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'var(--primary, #10b981)',
                              fontWeight: '700',
                              cursor: 'pointer',
                              padding: 0,
                              textDecoration: 'underline'
                            }}
                          >
                            Đăng ký ngay
                          </button>
                        </p>
                      </form>
                    ) : (
                      /* PHẦN 2: FORM ĐĂNG KÝ */
                      <form onSubmit={handleRegisterSubmit}>
                        <h3 className="section-title" style={{ marginBottom: '6px' }}>
                          ✨ Tạo tài khoản mới
                        </h3>
                        <p
                          style={{
                            color: 'var(--text-muted)',
                            fontSize: '0.9rem',
                            marginBottom: '20px'
                          }}
                        >
                          Thiết lập tên đăng nhập và mật khẩu để lưu kết quả trên Supabase.
                        </p>

                        <div className="form-group">
                          <label>Tên đăng nhập</label>
                          <input
                            type="text"
                            name="username"
                            value={authForm.username}
                            onChange={handleAuthInputChange}
                            placeholder="VD: minhanh_11a1"
                            autoComplete="username"
                          />
                          <small
                            style={{
                              display: 'block',
                              marginTop: '5px',
                              fontSize: '0.78rem',
                              color: 'var(--text-muted)'
                            }}
                          >
                            Từ 3–30 ký tự, gồm chữ cái không dấu, số, dấu (.) hoặc (_).
                          </small>
                        </div>

                        <div className="form-group">
                          <label>Mật khẩu</label>
                          <div style={{ position: 'relative' }}>
                            <input
                              type={showPassword ? 'text' : 'password'}
                              name="password"
                              value={authForm.password}
                              onChange={handleAuthInputChange}
                              placeholder="Tối thiểu 6 ký tự..."
                              autoComplete="new-password"
                              style={{ paddingRight: '44px' }}
                            />
                            <button
                              type="button"
                              onClick={() => setShowPassword(!showPassword)}
                              aria-label="Hiện hoặc ẩn mật khẩu"
                              style={{
                                position: 'absolute',
                                right: '10px',
                                top: '50%',
                                transform: 'translateY(-50%)',
                                background: 'transparent',
                                border: 'none',
                                cursor: 'pointer',
                                fontSize: '1.1rem',
                                color: 'var(--text-muted)'
                              }}
                            >
                              {showPassword ? '🙈' : '👁️'}
                            </button>
                          </div>

                          {/* Thanh đo độ mạnh mật khẩu */}
                          {authForm.password && (
                            <div style={{ marginTop: '8px' }}>
                              <div
                                style={{
                                  display: 'flex',
                                  gap: '6px',
                                  height: '5px',
                                  marginBottom: '4px'
                                }}
                              >
                                {[1, 2, 3].map((lvl) => (
                                  <div
                                    key={lvl}
                                    style={{
                                      flex: 1,
                                      borderRadius: '999px',
                                      background:
                                        passwordStrength.score >= lvl
                                          ? passwordStrength.color
                                          : 'rgba(148, 163, 184, 0.25)'
                                    }}
                                  />
                                ))}
                              </div>
                              <span
                                style={{
                                  fontSize: '0.78rem',
                                  fontWeight: '600',
                                  color: passwordStrength.color
                                }}
                              >
                                Độ mạnh mật khẩu: {passwordStrength.label}
                              </span>
                            </div>
                          )}
                        </div>

                        <div className="form-group">
                          <label>Xác nhận mật khẩu</label>
                          <div style={{ position: 'relative' }}>
                            <input
                              type={showConfirmPassword ? 'text' : 'password'}
                              name="confirmPassword"
                              value={authForm.confirmPassword}
                              onChange={handleAuthInputChange}
                              placeholder="Nhập lại mật khẩu..."
                              autoComplete="new-password"
                              style={{ paddingRight: '44px' }}
                            />
                            <button
                              type="button"
                              onClick={() =>
                                setShowConfirmPassword(!showConfirmPassword)
                              }
                              aria-label="Hiện hoặc ẩn mật khẩu xác nhận"
                              style={{
                                position: 'absolute',
                                right: '10px',
                                top: '50%',
                                transform: 'translateY(-50%)',
                                background: 'transparent',
                                border: 'none',
                                cursor: 'pointer',
                                fontSize: '1.1rem',
                                color: 'var(--text-muted)'
                              }}
                            >
                              {showConfirmPassword ? '🙈' : '👁️'}
                            </button>
                          </div>
                          {authForm.confirmPassword && (
                            <small
                              style={{
                                display: 'block',
                                marginTop: '5px',
                                fontSize: '0.78rem',
                                fontWeight: '600',
                                color:
                                  authForm.password === authForm.confirmPassword
                                    ? '#10b981'
                                    : '#ef4444'
                              }}
                            >
                              {authForm.password === authForm.confirmPassword
                                ? '✓ Mật khẩu xác nhận trùng khớp'
                                : '✗ Mật khẩu xác nhận chưa khớp'}
                            </small>
                          )}
                        </div>

                        <button type="submit" className="btn-primary" disabled={loading}>
                          {loading ? 'Đang khởi tạo tài khoản...' : 'Đăng ký tài khoản ✨'}
                        </button>

                        <p
                          style={{
                            textAlign: 'center',
                            marginTop: '18px',
                            fontSize: '0.9rem',
                            color: 'var(--text-muted)'
                          }}
                        >
                          Đã có tài khoản?{' '}
                          <button
                            type="button"
                            onClick={() => switchAuthTab('login')}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'var(--primary, #10b981)',
                              fontWeight: '700',
                              cursor: 'pointer',
                              padding: 0,
                              textDecoration: 'underline'
                            }}
                          >
                            Đăng nhập
                          </button>
                        </p>
                      </form>
                    )}
                  </div>
                ) : (
                  /* SAU KHI ĐĂNG NHẬP / ĐĂNG KÝ: NHẬP THÔNG TIN KHẢO SÁT */
                  <div>
                    <h3 className="section-title">📋 Thông tin khảo sát</h3>
                    <div className="form-group">
                      <label>Họ và tên học sinh</label>
                      <input
                        type="text"
                        id="name"
                        value={userInfo.name}
                        onChange={handleInfoChange}
                        placeholder="Nhập họ tên..."
                      />
                    </div>
                    <div className="form-group">
                      <label>Trường học</label>
                      <input
                        type="text"
                        id="school"
                        value={userInfo.school}
                        onChange={handleInfoChange}
                        placeholder="Nhập tên trường..."
                      />
                    </div>
                    <div className="form-grid">
                      <div className="form-group">
                        <label>Khối lớp</label>
                        <select id="grade" value={userInfo.grade} onChange={handleInfoChange}>
                          <option value="10">Khối 10</option>
                          <option value="11">Khối 11</option>
                          <option value="12">Khối 12</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label>Giới tính</label>
                        <select id="gender" value={userInfo.gender} onChange={handleInfoChange}>
                          <option value="Nam">Nam</option>
                          <option value="Nữ">Nữ</option>
                        </select>
                      </div>
                    </div>

                    <div className="form-group range-group">
                      <label style={{ margin: 0 }}>
                        Thời gian sử dụng TB/ngày: <strong>{userInfo.hours} giờ/ngày</strong>
                      </label>
                      <input
                        type="range"
                        id="hours"
                        min="0"
                        max="24"
                        step="0.5"
                        value={userInfo.hours}
                        onChange={handleInfoChange}
                        className="slider"
                      />
                    </div>

                    <button className="btn-primary" onClick={handleStartSurveyAfterProfile}>
                      Bắt đầu trả lời 10 câu hỏi SAS-SV 🚀
                    </button>
                  </div>
                )}
              </div>
            )}

            {step >= 1 && step <= 10 && (
              <div className="fade-in question-container">
                <span className="question-counter">
                  Câu hỏi {step} / {QUESTIONS.length}
                </span>
                <h2 className="question-text">{QUESTIONS[step - 1]}</h2>

                <div className="options-wrapper">
                  <span className="label-hint left">Rất không đồng ý</span>
                  <div className="options-flex">
                    {[1, 2, 3, 4, 5, 6].map((num) => (
                      <label
                        key={num}
                        className={`option-card ${answers[`Q${step}`] === num ? 'selected' : ''}`}
                      >
                        <input
                          type="radio"
                          name={`Q${step}`}
                          value={num}
                          checked={answers[`Q${step}`] === num}
                          onChange={() => handleOptionChange(step, num)}
                        />
                        <span className="num-text">{num}</span>
                      </label>
                    ))}
                  </div>
                  <span className="label-hint right">Rất đồng ý</span>
                </div>

                <div className="nav-buttons">
                  <button className="btn-secondary" onClick={prevStep}>
                    Quay lại
                  </button>
                  {step < 10 ? (
                    <button className="btn-primary" onClick={nextStep}>
                      Tiếp theo ➡️
                    </button>
                  ) : (
                    <button className="btn-accent" onClick={submitSurvey} disabled={loading}>
                      {loading ? 'Mô hình đang sàng lọc...' : 'Xem Kết Quả Sàng Lọc 🧠'}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {step === 11 && resultData && (
          <div className="fade-in result-page-container">
            {!geminiAdvice && (
              <div className="card text-center standard-result-view">
                <div className="success-icon">🎯</div>
                <h3>Kết quả sàng lọc của {userInfo.name}</h3>
                <p className="school-tag">
                  Trường: {userInfo.school} - Khối {userInfo.grade} • Thời gian TB: {userInfo.hours}h/ngày
                </p>

                <div
                  className="result-badge-custom-fix"
                  style={{
                    padding: '14px 28px',
                    borderRadius: '12px',
                    display: 'inline-block',
                    margin: '18px 0',
                    fontWeight: '800',
                    fontSize: '1.4rem',
                    textTransform: 'uppercase',
                    border: getBadgeStyle(resultData.result).border,
                    color: getBadgeStyle(resultData.result).color,
                    backgroundColor: getBadgeStyle(resultData.result).bg
                  }}
                >
                  Mức độ nguy cơ: {resultData.result}
                </div>

                <p
                  style={{
                    fontSize: '0.88rem',
                    color: 'var(--text-muted)',
                    background: 'rgba(245, 158, 11, 0.08)',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                    marginTop: '12px',
                    lineHeight: '1.55',
                    textAlign: 'left'
                  }}
                >
                  ℹ️ <strong>Lưu ý giới hạn:</strong> Kết quả của hệ thống chỉ mang tính sàng lọc và hỗ trợ giáo dục thói quen sử dụng điện thoại, không phải kết luận chẩn đoán y khoa hay điều trị tâm lý.
                </p>

                <div
                  className="feedback-container"
                  style={{
                    margin: '25px 0',
                    padding: '18px',
                    background: 'rgba(255,255,255,0.04)',
                    borderRadius: '12px'
                  }}
                >
                  <p style={{ fontWeight: '600', marginBottom: '12px' }}>
                    Đánh giá mức độ hài lòng với kết quả sàng lọc{' '}
                    <span style={{ color: '#ff6b6b' }}>*</span>
                  </p>
                  <div
                    className="star-flex"
                    style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}
                  >
                    {[1, 2, 3, 4, 5].map((num) => (
                      <span
                        key={num}
                        style={{
                          fontSize: '2.3rem',
                          cursor: hasRated ? 'not-allowed' : 'pointer',
                          color: selectedStars >= num ? '#fbbf24' : '#4b5563'
                        }}
                        onMouseEnter={() => !hasRated && setSelectedStars(num)}
                        onClick={() => handleMainRatingSubmit(num)}
                      >
                        ★
                      </span>
                    ))}
                  </div>
                  {hasRated && (
                    <p style={{ fontSize: '0.9rem', color: '#10b981', marginTop: '10px' }}>
                      ✅ Đã xác nhận đánh giá thành công!
                    </p>
                  )}
                </div>

                <div
                  className="gemini-trigger-zone-block"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    alignItems: 'center'
                  }}
                >
                  {!geminiLoading && (
                    <button
                      className="btn-primary gemini-btn"
                      onClick={fetchGeminiAdvice}
                      disabled={!hasRated}
                      style={{
                        width: '100%',
                        maxWidth: '360px',
                        opacity: hasRated ? 1 : 0.4
                      }}
                    >
                      ✨ Nhận hỗ trợ giáo dục cá nhân hóa {!hasRated && '🔒'}
                    </button>
                  )}

                  {geminiLoading && (
                    <div className="ai-loading-card">
                      <div className="magic-spinner">🌱</div>
                      <p>Hệ thống đang tổng hợp lịch sử &amp; kho tri thức giáo dục...</p>
                    </div>
                  )}

                  {geminiError && <p className="error-text-glow">❌ {geminiError}</p>}

                  <button
                    className="btn-secondary"
                    onClick={resetSurvey}
                    disabled={!hasRated}
                    style={{
                      width: '100%',
                      maxWidth: '360px',
                      opacity: hasRated ? 1 : 0.4
                    }}
                  >
                    Thực hiện lại khảo sát 🔄 {!hasRated && '🔒'}
                  </button>
                </div>
              </div>
            )}

            {geminiAdvice && (
              <GeminiAdvice
                initialAdvice={geminiAdvice}
                userInfo={userInfo}
                resultLevel={resultData.result}
                predictedLevel={resultData.predicted_level}
                surveyAnswers={answers}
                userCode={currentUser?.user_code}
                userEmail={currentUser?.email}
                onBack={() => setGeminiAdvice(null)}
              />
            )}
          </div>
        )}
      </main>

      <footer
        className="footer-section"
        style={{ marginTop: '35px', textAlign: 'center', padding: '15px 0' }}
      >
        <span
          style={{
            background: 'rgba(16, 185, 129, 0.12)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            padding: '8px 20px',
            borderRadius: '20px',
            fontSize: '0.95rem',
            fontWeight: '600',
            color: '#10b981',
            display: 'inline-block'
          }}
        >
          👥 Tổng số lượt đã tham gia khảo sát: <strong>{userCount}</strong> lượt
        </span>
      </footer>
    </div>
  );
}

export default App;