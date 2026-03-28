export default function SentenceTranslationExercise({ exercise, answer, onAnswerChange, exercisePosition }) {
  if (exercise?.options && exercise.options.length > 1) {
    return (
      <div className="mt-3 flex flex-wrap gap-2">
        {exercise.options.map((option) => {
          const selected = answer === option;
          return (
            <button
              key={`${exercisePosition}-${option}`}
              type="button"
              onClick={() => onAnswerChange(option)}
              className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${
                selected ? "border-blue-600 bg-blue-600 text-white" : "border-[var(--line)] bg-white hover:bg-blue-50"
              }`}
            >
              {option}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <textarea
      className="field mt-3"
      rows={4}
      placeholder="Введите перевод..."
      value={answer}
      onChange={(event) => onAnswerChange(event.target.value)}
    />
  );
}
