import LoadingSpinner from "../components/LoadingSpinner";
import DefinitionMatchExercise from "../components/training/DefinitionMatchExercise";
import SentenceTranslationExercise from "../components/training/SentenceTranslationExercise";
import WordScrambleExercise from "../components/training/WordScrambleExercise";
import { useTrainingSession } from "../hooks/useTrainingSession";

const MODE_META = {
  sentence_translation_full: {
    title: "Перевод предложения",
    hint: "Пиши полный перевод предложения на русский язык.",
  },
  word_definition_match: {
    title: "Сопоставление с определением",
    hint: "Выбери определение, которое подходит к слову.",
  },
  word_scramble: {
    title: "Собери слово",
    hint: "Нажимай на буквы, чтобы собрать английское слово.",
  },
};

export default function TrainingPage({ onError }) {
  const {
    answerReady,
    currentAnswer,
    currentExercise,
    currentIndex,
    generationNote,
    isTrainingActive,
    loadingCurrent,
    loadingPrefetch,
    mode,
    progressPercent,
    resetSessionState,
    sessionResult,
    setCurrentAnswer,
    setMode,
    setSize,
    size,
    startTraining,
    submitCurrentAndContinue,
  } = useTrainingSession({ onError });

  function renderExercise() {
    if (!currentExercise) {
      return null;
    }

    if (currentExercise.exercise_type === "word_scramble") {
      return (
        <WordScrambleExercise
          exercise={currentExercise}
          exercisePosition={currentIndex}
          onAnswerChange={setCurrentAnswer}
        />
      );
    }

    if (currentExercise.exercise_type === "word_definition_match") {
      return (
        <DefinitionMatchExercise
          exercise={currentExercise}
          exercisePosition={currentIndex}
          onAnswerChange={setCurrentAnswer}
        />
      );
    }

    return (
      <SentenceTranslationExercise
        exercise={currentExercise}
        answer={currentAnswer}
        onAnswerChange={setCurrentAnswer}
        exercisePosition={currentIndex}
      />
    );
  }

  return (
    <section className="space-y-4">
      {loadingCurrent ? <LoadingSpinner message="Генерирую упражнения..." estimatedSeconds="3-8" /> : null}

      <header className="surface p-4 md:p-5">
        <p className="kicker">Training</p>
        <h2 className="section-title">Тренировка</h2>
        <p className="muted mt-1 text-sm">Выберите формат, количество заданий и пройдите сессию без ожиданий: следующие упражнения подгружаются заранее.</p>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="text-sm">
            Количество упражнений
            <input
              type="number"
              min={1}
              max={30}
              value={size}
              onChange={(event) => setSize(Number(event.target.value || 1))}
              className="field mt-1"
              disabled={isTrainingActive}
            />
          </label>
          <label className="text-sm md:col-span-2">
            Тип упражнений
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              className="field mt-1"
              disabled={isTrainingActive}
            >
              <option value="sentence_translation_full">Перевод предложения</option>
              <option value="word_definition_match">Сопоставление с определением</option>
              <option value="word_scramble">Собери слово</option>
            </select>
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button onClick={startTraining} className="btn-primary disabled:opacity-50" type="button" disabled={loadingCurrent || isTrainingActive}>
            {loadingCurrent ? "Подготовка..." : "Начать тренировку"}
          </button>
          {sessionResult ? (
            <button className="btn-secondary" type="button" onClick={resetSessionState}>
              Новая сессия
            </button>
          ) : null}
          {isTrainingActive ? <span className="chip">Задание {currentIndex + 1} из {size}</span> : null}
          {generationNote ? <span className="chip">{generationNote}</span> : null}
        </div>
      </header>

      {isTrainingActive ? (
        <section className="surface p-4 md:p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="kicker">Текущий режим</p>
              <h3 className="text-lg font-extrabold text-gray-900">{MODE_META[mode].title}</h3>
              <p className="muted text-sm">{MODE_META[mode].hint}</p>
            </div>
            <span className="chip">{progressPercent}%</span>
          </div>
          <div className="mt-3 h-2 rounded-full bg-gray-200">
            <div className="h-2 rounded-full bg-blue-600 transition-all" style={{ width: `${progressPercent}%` }} />
          </div>
        </section>
      ) : null}

      {isTrainingActive && currentExercise ? (
        <article className="surface p-4 md:p-5">
          <p className="text-base font-semibold">{currentExercise.prompt}</p>
          {renderExercise()}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button onClick={submitCurrentAndContinue} className="btn-primary disabled:opacity-50" type="button" disabled={loadingCurrent || !answerReady}>
              {currentIndex + 1 >= size ? "Завершить и отправить" : "Следующее задание"}
            </button>
            {loadingPrefetch ? <span className="chip">Подгружаю следующую партию...</span> : null}
          </div>
        </article>
      ) : null}

      {sessionResult ? (
        <section className="surface p-4 md:p-5">
          <p className="text-lg font-extrabold text-gray-900">
            Результат: {sessionResult.session.correct}/{sessionResult.session.total}
          </p>
          <p className="muted mt-1 text-sm">Точность: {Math.round(Number(sessionResult.session.accuracy) * 100)}%</p>
          {sessionResult.incorrect_feedback.length > 0 ? (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
              {sessionResult.incorrect_feedback.map((item) => (
                <li key={item.exercise_id}>{item.explanation_ru}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-green-700">Отлично, ошибок нет.</p>
          )}
          {sessionResult.advice_feedback?.length > 0 ? (
            <div className="mt-4">
              <p className="text-sm font-semibold text-gray-900">Рекомендации по стилю</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                {sessionResult.advice_feedback.map((item) => (
                  <li key={`advice-${item.exercise_id}`}>{item.explanation_ru}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
