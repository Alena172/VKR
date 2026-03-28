import { useEffect, useState } from "react";

function buildAssembleOptions(exercise) {
  if (!exercise || exercise.exercise_type !== "word_scramble") {
    return [];
  }
  const answer = (exercise.answer || "").trim();
  if (!answer || answer.includes(" ") || answer.includes("-")) {
    return [];
  }
  if (
    exercise.options &&
    exercise.options.length === answer.length &&
    exercise.options.every((opt) => typeof opt === "string" && opt.length === 1 && /^[a-zA-Z]$/.test(opt))
  ) {
    return exercise.options.map((opt) => opt.toUpperCase());
  }
  const letters = answer.split("").map((ch) => ch.toUpperCase());
  const pivot = Math.max(1, Math.floor(letters.length / 2));
  const scrambled = [...letters.slice(pivot), ...letters.slice(0, pivot)];
  return scrambled.join("").toLowerCase() === answer.toLowerCase() ? [...letters].reverse() : scrambled;
}

export default function WordScrambleExercise({ exercise, exercisePosition, onAnswerChange }) {
  const [selected, setSelected] = useState([]);
  const [available, setAvailable] = useState([]);

  useEffect(() => {
    if (!exercise || exercise.exercise_type !== "word_scramble") {
      setSelected([]);
      setAvailable([]);
      onAnswerChange("");
      return;
    }
    const options = buildAssembleOptions(exercise);
    const letters = options.map((char, idx) => ({
      id: `${exercisePosition}-${idx}-${char}`,
      char,
      originalIndex: idx,
    }));
    setSelected([]);
    setAvailable(letters);
    onAnswerChange("");
  }, [exercise, exercisePosition, onAnswerChange]);

  useEffect(() => {
    onAnswerChange(selected.map((item) => item.char).join(""));
  }, [onAnswerChange, selected]);

  function pickLetter(letterId) {
    setAvailable((prevAvailable) => {
      const letter = prevAvailable.find((item) => item.id === letterId);
      if (!letter) {
        return prevAvailable;
      }
      setSelected((prevSelected) => [...prevSelected, letter]);
      return prevAvailable.filter((item) => item.id !== letterId);
    });
  }

  function unpickLetter(letterId) {
    setSelected((prevSelected) => {
      const letter = prevSelected.find((item) => item.id === letterId);
      if (!letter) {
        return prevSelected;
      }
      setAvailable((prevAvailable) => [...prevAvailable, letter].sort((a, b) => a.originalIndex - b.originalIndex));
      return prevSelected.filter((item) => item.id !== letterId);
    });
  }

  function resetPickedLetters() {
    if (!selected.length) {
      return;
    }
    setAvailable((prevAvailable) => [...prevAvailable, ...selected].sort((a, b) => a.originalIndex - b.originalIndex));
    setSelected([]);
  }

  return (
    <div className="mt-3 space-y-3">
      <div className="surface-strong p-3 text-sm">
        Собранное слово: <span className="font-extrabold text-gray-900">{selected.map((item) => item.char).join("") || "—"}</span>
      </div>

      <div className="rounded-xl border-2 border-dashed border-gray-300 bg-white px-3 py-2 text-sm">
        <p className="muted mb-2 text-xs">Собираем слово (клик по букве возвращает её обратно)</p>
        <div className="flex min-h-10 flex-wrap gap-2">
          {selected.length ? (
            selected.map((letter) => (
              <button
                key={`selected-${letter.id}`}
                type="button"
                onClick={() => unpickLetter(letter.id)}
                className="rounded-lg border-2 border-blue-400 bg-blue-500 px-3 py-1.5 text-sm font-semibold text-white"
              >
                {letter.char}
              </button>
            ))
          ) : (
            <span className="muted">Пока пусто</span>
          )}
        </div>
      </div>

      <div className="rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 px-3 py-2 text-sm">
        <p className="muted mb-2 text-xs">Доступные буквы</p>
        <div className="flex min-h-10 flex-wrap gap-2">
          {available.length ? (
            available.map((letter) => (
              <button
                key={`available-${letter.id}`}
                type="button"
                onClick={() => pickLetter(letter.id)}
                className="rounded-lg border-2 border-blue-300 bg-white px-3 py-1.5 text-sm font-semibold text-blue-700 hover:bg-blue-50"
              >
                {letter.char}
              </button>
            ))
          ) : (
            <span className="muted">Все буквы использованы</span>
          )}
        </div>
      </div>

      <button type="button" onClick={resetPickedLetters} className="btn-secondary">
        Сбросить буквы
      </button>
    </div>
  );
}
