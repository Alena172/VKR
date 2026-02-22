import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

const FLIP_ANIMATION_MS = 520;

export default function ReviewPage({ onError }) {
  const [plan, setPlan] = useState(null);
  const [summary, setSummary] = useState(null);

  const [sessionSize, setSessionSize] = useState(20);
  const [sessionMode, setSessionMode] = useState(null); // "srs" | "random" | null
  const [sessionItems, setSessionItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [sessionCorrect, setSessionCorrect] = useState(0);
  const [sessionIncorrect, setSessionIncorrect] = useState(0);
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sessionMessage, setSessionMessage] = useState("");

  async function loadReviewMeta() {
    try {
      const [planData, summaryData] = await Promise.all([api.reviewPlan(10), api.reviewSummary()]);
      setPlan(planData);
      setSummary(summaryData);
    } catch (error) {
      onError(error.message);
    }
  }

  useEffect(() => {
    loadReviewMeta();
  }, []);

  const currentItem = useMemo(() => {
    if (!sessionItems.length || currentIndex >= sessionItems.length) {
      return null;
    }
    return sessionItems[currentIndex];
  }, [sessionItems, currentIndex]);

  const isSessionActive = sessionMode !== null;
  const sessionFinished = isSessionActive && (sessionItems.length === 0 || currentIndex >= sessionItems.length);

  async function startSession(mode) {
    setStarting(true);
    setSessionMessage("");
    onError("");
    try {
      const data = await api.reviewStartSession({ mode, size: sessionSize });
      setSessionMode(mode);
      setSessionItems(data.items || []);
      setCurrentIndex(0);
      setIsFlipped(false);
      setSessionCorrect(0);
      setSessionIncorrect(0);

      if (!data.items || data.items.length === 0) {
        setSessionMessage(mode === "srs" ? "Сейчас нет слов для SRS-повторения." : "В словаре нет слов для случайной сессии.");
      }
    } catch (error) {
      onError(error.message);
    } finally {
      setStarting(false);
    }
  }

  async function submitAnswer(isCorrect) {
    if (!currentItem || submitting) {
      return;
    }
    setSubmitting(true);
    onError("");
    try {
      const submitPromise =
        sessionMode === "srs"
          ? api.reviewQueueSubmit({ word: currentItem.word, is_correct: isCorrect })
          : Promise.resolve();

      // First finish flip animation on the current card,
      // then switch to the next word to avoid visual leakage.
      setIsFlipped(false);
      await Promise.all([submitPromise, wait(FLIP_ANIMATION_MS)]);

      if (isCorrect) {
        setSessionCorrect((prev) => prev + 1);
      } else {
        setSessionIncorrect((prev) => prev + 1);
      }
      setCurrentIndex((prev) => prev + 1);
    } catch (error) {
      onError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  function resetSession() {
    setSessionMode(null);
    setSessionItems([]);
    setCurrentIndex(0);
    setIsFlipped(false);
    setSessionCorrect(0);
    setSessionIncorrect(0);
    setSessionMessage("");
  }

  return (
    <section className="space-y-6">
      {!isSessionActive ? (
        <>
          <header className="surface p-4 md:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="kicker">Spaced Repetition</p>
                <h2 className="section-title">Сессии повторения</h2>
                <p className="muted mt-1 text-sm">Запусти SRS-сессию или случайную сессию вне SRS.</p>
              </div>
              <button className="btn-secondary" onClick={loadReviewMeta} type="button">
                Обновить
              </button>
            </div>
          </header>

          {summary ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard title="Всего слов в SRS" value={summary.total_tracked} />
              <StatCard title="К повторению сейчас" value={summary.due_now} />
              <StatCard title="Хорошо закреплены" value={summary.mastered} />
              <StatCard title="Вызывают трудности" value={summary.troubled} />
            </div>
          ) : null}

          <section className="surface p-4 md:p-5 space-y-4">
            <div className="grid gap-3 md:grid-cols-[220px_1fr]">
              <label className="text-sm">
                Размер сессии
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={sessionSize}
                  onChange={(e) => setSessionSize(Number(e.target.value || 1))}
                  className="field mt-1"
                  disabled={starting}
                />
              </label>
              <div className="flex flex-wrap items-end gap-2">
                <button type="button" className="btn-primary" onClick={() => startSession("srs")} disabled={starting}>
                  Запустить SRS-сессию
                </button>
                <button type="button" className="btn-secondary" onClick={() => startSession("random")} disabled={starting}>
                  Случайная сессия
                </button>
              </div>
            </div>
            {plan ? (
              <p className="text-sm text-gray-600">
                План: к повторению сейчас — {plan.due_count}, запланировано на ближайшее время — {plan.upcoming_count}. Рекомендуемые слова: {plan.recommended_words.join(", ") || "-"}
              </p>
            ) : null}
          </section>
        </>
      ) : null}

      {isSessionActive ? (
        <section className="surface p-4 md:p-6">
          <div className="mx-auto max-w-3xl space-y-4">
            <div className="relative z-20 rounded-lg bg-white/95 p-3 flex flex-wrap items-center justify-between gap-2 text-sm text-gray-600">
              <span>
                Режим: <strong>{sessionMode === "srs" ? "Интервальное повторение (SRS)" : "Случайная сессия"}</strong>
              </span>
              <span>
                {Math.min(currentIndex, sessionItems.length)} / {sessionItems.length}
              </span>
              <span>
                Помню: <strong className="text-green-700">{sessionCorrect}</strong> · Не помню:{" "}
                <strong className="text-red-700">{sessionIncorrect}</strong>
              </span>
              <button type="button" className="btn-secondary" onClick={resetSession}>
                Завершить
              </button>
            </div>

            {sessionMessage ? <p className="text-sm text-gray-600">{sessionMessage}</p> : null}

            {currentItem ? (
              <div className="relative z-0 mt-2 flex w-full justify-center">
                <div className="w-full max-w-2xl">
                  <div className="relative h-[22rem] w-full overflow-hidden rounded-xl perspective-1000 isolate">
                  <div
                    className="relative h-full w-full preserve-3d transition-transform duration-500"
                    style={{ transform: isFlipped ? "rotateY(180deg)" : "rotateY(0deg)" }}
                  >
                    <div className="absolute inset-0 backface-hidden rounded-xl">
                      <div className="h-full rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 to-indigo-50 shadow-lg">
                        <div className="card-body flex h-full flex-col items-center justify-center text-center p-8">
                          <span className="mb-4 rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800">
                            Слово для изучения
                          </span>
                          <p className="text-4xl font-bold text-gray-900 break-all">{currentItem.word}</p>
                          {currentItem.context_definition ? (
                            <p className="mt-4 max-w-xl text-base leading-relaxed text-gray-700">{currentItem.context_definition}</p>
                          ) : null}
                          <button
                            type="button"
                            className="btn-primary mt-8"
                            onClick={() => setIsFlipped(true)}
                            disabled={submitting}
                          >
                            Показать перевод
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="absolute inset-0 backface-hidden rotate-y-180 rounded-xl">
                      <div className="h-full rounded-xl border border-green-200 bg-gradient-to-br from-green-50 to-emerald-50 shadow-lg">
                        <div className="card-body flex h-full flex-col items-center justify-center text-center p-8">
                          <span className="mb-4 rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800">
                            Перевод
                          </span>
                          <p className="text-2xl font-bold text-gray-900 break-all">{currentItem.word}</p>
                          <p className="mt-2 text-2xl font-semibold text-green-700 break-all">
                            {currentItem.russian_translation || "Перевод не найден"}
                          </p>
                          {currentItem.context_definition ? (
                            <p className="mt-4 max-w-xl text-base leading-relaxed text-gray-700">{currentItem.context_definition}</p>
                          ) : null}
                          <button
                            type="button"
                            className="btn-secondary mt-6"
                            onClick={() => setIsFlipped(false)}
                            disabled={submitting}
                          >
                            Смотреть снова
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              </div>
            ) : null}

            {currentItem && isFlipped && !sessionFinished ? (
              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <div className="text-center mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">Насколько легко вспомнить перевод?</h3>
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <button
                    type="button"
                    className="rounded-xl border-2 border-red-200 bg-red-50 p-4 text-left transition hover:bg-red-100"
                    onClick={() => submitAnswer(false)}
                    disabled={submitting}
                  >
                    <p className="text-base font-semibold text-red-700">Не помню</p>
                    <p className="mt-1 text-sm text-red-600">Совсем не вспомнил перевод</p>
                  </button>
                  <button
                    type="button"
                    className="rounded-xl border-2 border-green-200 bg-green-50 p-4 text-left transition hover:bg-green-100"
                    onClick={() => submitAnswer(true)}
                    disabled={submitting}
                  >
                    <p className="text-base font-semibold text-green-700">Помню</p>
                    <p className="mt-1 text-sm text-green-600">Сразу вспомнил перевод</p>
                  </button>
                </div>
              </div>
            ) : null}

            {sessionFinished ? (
              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h3 className="text-lg font-bold text-gray-900">Сессия завершена</h3>
                <p className="mt-2 text-sm text-gray-700">
                  Помню: <span className="font-semibold text-green-700">{sessionCorrect}</span>, не помню:{" "}
                  <span className="font-semibold text-red-700">{sessionIncorrect}</span>.
                </p>
                <div className="mt-3 flex gap-2">
                  <button type="button" className="btn-primary" onClick={() => startSession(sessionMode)}>
                    Повторить режим
                  </button>
                  <button type="button" className="btn-secondary" onClick={resetSession}>
                    Выйти
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </section>
  );
}

function StatCard({ title, value }) {
  return (
    <div className="surface p-3">
      <div className="muted text-xs">{title}</div>
      <div className="text-2xl font-extrabold text-gray-900">{value}</div>
    </div>
  );
}

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
