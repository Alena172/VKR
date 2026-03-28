import { useEffect, useState } from "react";
import { api, getErrorMessage, isAbortError } from "../lib/api";
import { useAbortControllers } from "../hooks/useAbortControllers";

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ru-RU");
}

export default function SessionsHistoryPage({ onError }) {
  const [sessions, setSessions] = useState([]);
  const [total, setTotal] = useState(0);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [answers, setAnswers] = useState([]);
  const [loadingAnswers, setLoadingAnswers] = useState(false);
  const [minAccuracy, setMinAccuracy] = useState("");
  const [maxAccuracy, setMaxAccuracy] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const { registerController, releaseController } = useAbortControllers();

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);

  async function loadSessions(targetPage = safePage) {
    setLoadingSessions(true);
    const controller = registerController();
    try {
      const offset = (targetPage - 1) * pageSize;
      const data = await api.listSessionsMe({
        limit: pageSize,
        offset,
        min_accuracy: minAccuracy,
        max_accuracy: maxAccuracy,
        date_from: dateFrom,
        date_to: dateTo,
      }, { signal: controller.signal });
      setSessions(data.items);
      setTotal(data.total);
      const nextTotalPages = Math.max(1, Math.ceil(data.total / pageSize));
      if (targetPage > nextTotalPages) {
        setPage(nextTotalPages);
      }
      if (data.items.length === 0) {
        setSelectedSessionId(null);
        setAnswers([]);
      }
    } catch (error) {
      if (!isAbortError(error)) {
        onError(getErrorMessage(error));
      }
    } finally {
      releaseController(controller);
      setLoadingSessions(false);
    }
  }

  async function loadAnswers(sessionId) {
    setLoadingAnswers(true);
    const controller = registerController();
    try {
      const data = await api.listSessionAnswersMe(sessionId, { signal: controller.signal });
      setSelectedSessionId(sessionId);
      setAnswers(data);
    } catch (error) {
      if (!isAbortError(error)) {
        onError(getErrorMessage(error));
      }
    } finally {
      releaseController(controller);
      setLoadingAnswers(false);
    }
  }

  function resetFilters() {
    setMinAccuracy("");
    setMaxAccuracy("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  useEffect(() => {
    loadSessions(safePage);
  }, [page, pageSize, minAccuracy, maxAccuracy, dateFrom, dateTo]);

  return (
    <section className="space-y-4">
      <header className="surface p-4 md:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="kicker">History</p>
            <h2 className="section-title">История сессий</h2>
          </div>
          <button className="btn-secondary" onClick={() => loadSessions(safePage)} type="button">
            Обновить
          </button>
        </div>
      </header>

      <section className="surface p-4 md:p-5">
        <div className="grid gap-3 md:grid-cols-5">
          <label className="text-sm">
            Min accuracy
            <input type="number" min={0} max={1} step="0.01" value={minAccuracy} onChange={(e) => setMinAccuracy(e.target.value)} className="field mt-1" placeholder="0.0" />
          </label>
          <label className="text-sm">
            Max accuracy
            <input type="number" min={0} max={1} step="0.01" value={maxAccuracy} onChange={(e) => setMaxAccuracy(e.target.value)} className="field mt-1" placeholder="1.0" />
          </label>
          <label className="text-sm">
            Дата с
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="field mt-1" />
          </label>
          <label className="text-sm">
            Дата по
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="field mt-1" />
          </label>
          <label className="text-sm">
            На страницу
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              className="field mt-1"
            >
              {[5, 10, 20, 50].map((size) => (
                <option key={size} value={size}>{size}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-3">
          <button type="button" className="btn-secondary" onClick={resetFilters}>Сбросить</button>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="surface p-4 md:p-5">
          <h3 className="text-base font-extrabold text-gray-900">Сессии ({total})</h3>
          {loadingSessions ? <p className="muted mb-2 mt-2 text-sm">Загрузка...</p> : null}
          <ul className="mt-2 space-y-2">
            {sessions.map((session) => (
              <li key={session.id} className={`rounded-xl border p-3 ${selectedSessionId === session.id ? "border-blue-600 bg-blue-50" : "border-[var(--line)] bg-white"}`}>
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm">
                    <div className="font-extrabold text-gray-900">Сессия #{session.id}</div>
                    <div className="muted">{formatDate(session.created_at)}</div>
                    <div className="text-[var(--text)]">{session.correct}/{session.total} (accuracy {session.accuracy})</div>
                  </div>
                  <button type="button" className="btn-secondary" onClick={() => loadAnswers(session.id)}>Ответы</button>
                </div>
              </li>
            ))}
            {!loadingSessions && sessions.length === 0 ? <li className="muted text-sm">Сессий по фильтрам нет.</li> : null}
          </ul>
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="muted">Страница {safePage}/{totalPages}</span>
            <div className="flex gap-2">
              <button type="button" className="btn-secondary disabled:opacity-50" onClick={() => setPage((prev) => Math.max(1, prev - 1))} disabled={safePage <= 1}>Назад</button>
              <button type="button" className="btn-secondary disabled:opacity-50" onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))} disabled={safePage >= totalPages}>Вперед</button>
            </div>
          </div>
        </section>

        <section className="surface p-4 md:p-5">
          <h3 className="text-base font-extrabold text-gray-900">Ответы</h3>
          {loadingAnswers ? <p className="muted mt-2 text-sm">Загрузка...</p> : null}
          {!loadingAnswers && selectedSessionId === null ? <p className="muted mt-2 text-sm">Выберите сессию, чтобы посмотреть ответы.</p> : null}
          {!loadingAnswers && selectedSessionId !== null ? (
            <ul className="mt-2 space-y-2">
              {answers.map((answer) => (
                <li key={answer.id} className="rounded-xl border border-[var(--line)] bg-white p-3 text-sm">
                  <div className="font-semibold">{answer.prompt || "Без prompt"}</div>
                  <div className="mt-1 muted">Ожидалось: <span className="font-medium text-[var(--text)]">{answer.expected_answer || "-"}</span></div>
                  <div className="muted">Ответ: <span className="font-medium text-[var(--text)]">{answer.user_answer}</span></div>
                  <div className={answer.is_correct ? "text-green-700" : "text-red-700"}>{answer.is_correct ? "Верно" : "Ошибка"}</div>
                  {answer.explanation_ru ? <div className="mt-1 text-[var(--text)]">{answer.explanation_ru}</div> : null}
                </li>
              ))}
              {answers.length === 0 ? <li className="muted text-sm">В этой сессии нет ответов.</li> : null}
            </ul>
          ) : null}
        </section>
      </div>
    </section>
  );
}
