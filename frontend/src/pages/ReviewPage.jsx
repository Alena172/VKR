import { useReviewSession } from "../hooks/useReviewSession";

const STRATEGY_LABELS = {
  NeighborExpansion: "Соседние связи",
  ClusterDeepening: "Углубление кластера",
  WeakNodeReinforcement: "Усиление слабых узлов",
};

export default function ReviewPage({ onError }) {
  const {
    currentIndex,
    currentItem,
    graphAnchorsByLemma,
    graphRecommendations,
    isFlipped,
    isSessionActive,
    loadReviewMeta,
    plan,
    resetSession,
    sessionCorrect,
    sessionFinished,
    sessionIncorrect,
    sessionItems,
    sessionMessage,
    sessionMode,
    sessionSize,
    setIsFlipped,
    setSessionSize,
    startSession,
    starting,
    submitting,
    submitAnswer,
    summary,
  } = useReviewSession({ onError });

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

          <section className="surface space-y-4 p-4 md:p-5">
            <div className="grid gap-3 md:grid-cols-[220px_1fr]">
              <label className="text-sm">
                Размер сессии
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={sessionSize}
                  onChange={(event) => setSessionSize(Number(event.target.value || 1))}
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

            {graphRecommendations.length ? (
              <div className="space-y-2 rounded-xl border border-blue-100 bg-blue-50/50 p-3">
                <p className="text-sm font-semibold text-gray-900">Рекомендации из learning graph</p>
                <div className="space-y-2">
                  {graphRecommendations.map((item) => {
                    const strategyLabel = STRATEGY_LABELS[item.primary_strategy] || item.primary_strategy || "Без стратегии";
                    const anchors = graphAnchorsByLemma[item.english_lemma] || [];
                    return (
                      <div key={`graph-rec-${item.english_lemma}`} className="rounded-lg border border-blue-100 bg-white p-2">
                        <p className="text-sm font-semibold text-gray-900">
                          {item.english_lemma} - {item.russian_translation}
                        </p>
                        <p className="mt-1 text-xs text-gray-600">
                          Strategy source: <span className="font-semibold text-blue-700">{strategyLabel}</span>
                        </p>
                        {anchors.length ? (
                          <p className="mt-1 text-xs text-gray-600">
                            Anchors: {anchors.map((anchor) => `${anchor.english_lemma} (${anchor.russian_translation})`).join(", ")}
                          </p>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      {isSessionActive ? (
        <section className="surface p-4 md:p-6">
          <div className="mx-auto max-w-3xl space-y-4">
            <div className="relative z-20 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white/95 p-3 text-sm text-gray-600">
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
                  <div className="relative isolate h-[22rem] w-full overflow-hidden rounded-xl perspective-1000">
                    <div
                      className="relative h-full w-full preserve-3d transition-transform duration-500"
                      style={{ transform: isFlipped ? "rotateY(180deg)" : "rotateY(0deg)" }}
                    >
                      <div className="absolute inset-0 backface-hidden rounded-xl">
                        <div className="h-full rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 to-indigo-50 shadow-lg">
                          <div className="card-body flex h-full flex-col items-center justify-center p-8 text-center">
                            <span className="mb-4 rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800">
                              Слово для изучения
                            </span>
                            <p className="break-all text-4xl font-bold text-gray-900">{currentItem.word}</p>
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
                          <div className="card-body flex h-full flex-col items-center justify-center p-8 text-center">
                            <span className="mb-4 rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800">
                              Перевод
                            </span>
                            <p className="break-all text-2xl font-bold text-gray-900">{currentItem.word}</p>
                            <p className="mt-2 break-all text-2xl font-semibold text-green-700">
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
                <div className="mb-4 text-center">
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
