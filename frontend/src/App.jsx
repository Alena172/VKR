import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Activity, Award, BarChart3, BookMarked, BookOpen, Clock, Home, Plus, Target, TrendingUp } from "lucide-react";
import VocabularyPage from "./pages/VocabularyPage";
import ReviewPage from "./pages/ReviewPage";
import TrainingPage from "./pages/TrainingPage";
import SessionsHistoryPage from "./pages/SessionsHistoryPage";
import { useAbortControllers } from "./hooks/useAbortControllers";
import { api, clearAuthToken, getErrorMessage, isAbortError, setAuthToken } from "./lib/api";

const USER_ID_KEY = "vkr_user_id";
const AUTH_TOKEN_KEY = "vkr_auth_token";

const NAVIGATION = [
  { name: "Главная", href: "/", icon: Home },
  { name: "Словарь", href: "/vocabulary", icon: BookMarked },
  { name: "Упражнения", href: "/exercises", icon: Activity },
  { name: "Повторение", href: "/review", icon: BookOpen },
  { name: "История", href: "/history", icon: BarChart3 },
];

export default function App() {
  const [error, setError] = useState("");
  const [email, setEmail] = useState("student@example.com");
  const [name, setName] = useState("Student");
  const [cefr, setCefr] = useState("A2");
  const [authToken, setAuthTokenState] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY) || "");
  const [authStatus, setAuthStatus] = useState("");
  const [userId, setUserId] = useState(() => {
    const stored = localStorage.getItem(USER_ID_KEY);
    return stored ? Number(stored) : 0;
  });

  async function loginOrRegister(event) {
    event?.preventDefault();
    setError("");
    setAuthStatus("");
    try {
      const authData = await api.authLoginOrRegister({ email, full_name: name, cefr_level: cefr });
      setAuthToken(authData.access_token);
      setAuthTokenState(authData.access_token);
      setUserId(authData.user_id);
      localStorage.setItem(USER_ID_KEY, String(authData.user_id));
      setAuthStatus(authData.is_new_user ? `Создан новый пользователь #${authData.user_id}` : `Вход выполнен (#${authData.user_id})`);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  function logout() {
    clearAuthToken();
    setAuthTokenState("");
    setAuthStatus("");
    setUserId(0);
    localStorage.removeItem(USER_ID_KEY);
  }

  useEffect(() => {
    if (authToken && !userId) {
      api
        .authMe()
        .then((data) => {
          setUserId(data.user_id);
          localStorage.setItem(USER_ID_KEY, String(data.user_id));
        })
        .catch((e) => setError(getErrorMessage(e)));
    }
  }, [authToken, userId]);

  if (!userId) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="card max-w-3xl w-full">
          <div className="card-header">
            <h1 className="text-2xl font-bold text-primary-600">ContextVocab</h1>
            <p className="text-sm text-gray-600 mt-1">Вход в платформу изучения английского</p>
          </div>
          <div className="card-body">
            <form className="grid gap-3 md:grid-cols-4" onSubmit={loginOrRegister}>
              <input className="form-input" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
              <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Имя" />
              <select className="form-input" value={cefr} onChange={(e) => setCefr(e.target.value)}>
                {["A1", "A2", "B1", "B2", "C1", "C2"].map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
              <button className="btn-primary" type="submit">
                Продолжить
              </button>
            </form>
            {authStatus ? <p className="mt-3 text-xs text-success-700">{authStatus}</p> : null}
            {error ? <p className="mt-3 rounded-lg border border-error-200 bg-error-50 px-3 py-2 text-sm text-error-700">{error}</p> : null}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside className="w-64 bg-white shadow-lg border-r border-gray-200">
        <div className="p-6 border-b border-gray-200">
          <h1 className="text-2xl font-bold text-primary-600">ContextVocab</h1>
          <p className="text-sm text-gray-600 mt-1">Умный словарь</p>
          <p className="mt-3 inline-flex rounded-full bg-primary-50 px-2 py-1 text-xs font-semibold text-primary-700">ID: {userId}</p>
        </div>

        <nav className="p-4">
          {NAVIGATION.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.href}
                to={item.href}
                end={item.href === "/"}
                className={({ isActive }) =>
                  `flex items-center px-4 py-3 mb-2 rounded-lg transition-colors ${
                    isActive
                      ? "bg-primary-50 text-primary-600 border-r-2 border-primary-600"
                      : "text-gray-600 hover:bg-gray-100"
                  }`
                }
              >
                <Icon className="h-5 w-5 mr-3" />
                <span className="font-medium">{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="px-4 pb-4">
          <button type="button" onClick={logout} className="btn-secondary w-full">
            Выйти
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <Routes>
            <Route path="/" element={<HomePage onError={setError} />} />
            <Route path="/vocabulary" element={<VocabularyPage onError={setError} />} />
            <Route path="/exercises" element={<TrainingPage onError={setError} />} />
            <Route path="/review" element={<ReviewPage onError={setError} />} />
            <Route path="/history" element={<SessionsHistoryPage onError={setError} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

          {error ? (
            <div className="mt-6 rounded-lg border border-error-200 bg-error-50 px-4 py-3 text-sm text-error-700">{error}</div>
          ) : null}
        </div>
      </main>
    </div>
  );
}

function HomePage({ onError }) {
  const [stats, setStats] = useState({
    total_words: 0,
    in_learning: 0,
    due_now: 0,
    mastered: 0,
    sessions_total: 0,
  });
  const [loading, setLoading] = useState(true);
  const { registerController, releaseController } = useAbortControllers();

  useEffect(() => {
    async function loadDashboard() {
      setLoading(true);
      const controller = registerController();
      try {
        await api.cleanupContextGarbage({ signal: controller.signal });
        const [vocabulary, reviewSummary, sessions] = await Promise.all([
          api.listVocabularyMe({ signal: controller.signal }),
          api.reviewSummary({ signal: controller.signal }),
          api.listSessionsMe({ limit: 1, offset: 0 }, { signal: controller.signal }),
        ]);
        setStats({
          total_words: vocabulary.length,
          in_learning: Math.max(vocabulary.length - reviewSummary.mastered, 0),
          due_now: reviewSummary.due_now,
          mastered: reviewSummary.mastered,
          sessions_total: sessions.total,
        });
      } catch (e) {
        if (!isAbortError(e)) {
          onError(getErrorMessage(e));
        }
      } finally {
        releaseController(controller);
        setLoading(false);
      }
    }
    loadDashboard();
  }, [onError]);

  const statsCards = [
    { name: "Всего слов", value: stats.total_words, icon: BookOpen, iconWrap: "bg-blue-100", iconColor: "text-blue-600", description: "Слов в вашем словаре" },
    { name: "На изучении", value: stats.in_learning, icon: Clock, iconWrap: "bg-yellow-100", iconColor: "text-yellow-600", description: "Слов еще не выучено" },
    { name: "Для повторения", value: stats.due_now, icon: Target, iconWrap: "bg-orange-100", iconColor: "text-orange-600", description: "Слов готовы к повторению" },
    { name: "Выучено", value: stats.mastered, icon: Award, iconWrap: "bg-green-100", iconColor: "text-green-600", description: "Освоенные слова" },
  ];

  const quickActions = [
    { label: "Добавить слово", path: "/vocabulary", icon: Plus, description: "Добавить новое слово в словарь" },
    { label: "Начать тренировку", path: "/exercises", icon: Activity, description: "Продолжить практику упражнений" },
    { label: "Посмотреть прогресс", path: "/history", icon: TrendingUp, description: "Анализ ваших сессий и ошибок" },
  ];

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-bold text-gray-900">Добро пожаловать!</h1>
        <p className="text-gray-600 mt-2">Начните изучать английские слова с умным подходом</p>
        <p className="text-xs text-gray-500 mt-2">Завершено сессий: {stats.sessions_total}</p>
      </header>

      <section>
        <h2 className="text-2xl font-semibold text-gray-900 mb-6">Ваша статистика</h2>
        {loading ? (
          <div className="card p-6 text-gray-600">Загрузка...</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {statsCards.map((stat, index) => {
              const Icon = stat.icon;
              return (
                <div key={stat.name} className="card p-6 animate-fade-in" style={{ animationDelay: `${index * 100}ms` }}>
                  <div className="flex items-center">
                    <div className={`p-3 rounded-lg ${stat.iconWrap}`}>
                      <Icon className={`h-6 w-6 ${stat.iconColor}`} />
                    </div>
                    <div className="ml-4">
                      <p className="text-sm font-medium text-gray-600">{stat.name}</p>
                      <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                      <p className="text-xs text-gray-500 mt-1">{stat.description}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="actions-section">
        <h2 className="text-2xl font-semibold text-gray-900 mb-6">Быстрые действия</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {quickActions.map((action, index) => {
            const Icon = action.icon;
            return (
              <Link
                key={action.label}
                to={action.path}
                className="card p-6 hover:shadow-md transition-shadow duration-200 animate-slide-up block"
                style={{ animationDelay: `${index * 100}ms` }}
              >
                <div className="flex items-center mb-4">
                  <div className="p-2 rounded-lg bg-primary-100">
                    <Icon className="h-5 w-5 text-primary-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 ml-3">{action.label}</h3>
                </div>
                <p className="text-gray-600 text-sm">{action.description}</p>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}
