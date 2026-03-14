import { useEffect, useMemo, useRef, useState } from "react";
import { api, pollTask } from "../lib/api";
import LoadingSpinner from "../components/LoadingSpinner";

const PREFETCH_BATCH_SIZE = 2;

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
  const [size, setSize] = useState(6);
  const [mode, setMode] = useState("sentence_translation_full");
  const [currentExercise, setCurrentExercise] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [currentAnswer, setCurrentAnswer] = useState("");
  const [scrambleState, setScrambleState] = useState({ selected: [], available: [] });
  const [definitionMatchState, setDefinitionMatchState] = useState({
    words: [],
    definitions: [],
    mapping: {},
    selectedWord: null,
    selectedDefinition: null,
  });
  const matchBoardRef = useRef(null);
  const wordRefs = useRef({});
  const definitionRefs = useRef({});
  const [definitionLines, setDefinitionLines] = useState([]);
  const [bufferExercises, setBufferExercises] = useState([]);
  const [fetchedCount, setFetchedCount] = useState(0);
  const [submittedAnswers, setSubmittedAnswers] = useState([]);
  const [loadingCurrent, setLoadingCurrent] = useState(false);
  const [loadingPrefetch, setLoadingPrefetch] = useState(false);
  const [sessionResult, setSessionResult] = useState(null);
  const [isTrainingActive, setIsTrainingActive] = useState(false);
  const [generationNote, setGenerationNote] = useState("");

  const selectedLetters = scrambleState.selected;
  const availableLetters = scrambleState.available;

  const progressPercent = size > 0 ? Math.round((currentIndex / size) * 100) : 0;

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

  function initWordScrambleState(exercise, exercisePosition) {
    if (!exercise || exercise.exercise_type !== "word_scramble") {
      setScrambleState({ selected: [], available: [] });
      return;
    }
    const options = buildAssembleOptions(exercise);
    const letters = options.map((char, idx) => ({
      id: `${exercisePosition}-${idx}-${char}`,
      char,
      originalIndex: idx,
    }));
    setScrambleState({ selected: [], available: letters });
  }

  function extractWordsFromDefinitionPrompt(exercise) {
    if (!exercise || exercise.exercise_type !== "word_definition_match") {
      return [];
    }
    const prompt = (exercise.prompt || "").trim();
    if (!prompt) {
      return [];
    }

    const numberedMatches = [...prompt.matchAll(/\d+\.\s*([a-z][a-z'-]{0,48})/gi)].map((m) => m[1].toLowerCase());
    if (numberedMatches.length > 0) {
      return [...new Set(numberedMatches)];
    }

    const afterColon = prompt.split(":").pop()?.trim() || "";
    const singleWordMatch = afterColon.match(/([a-z][a-z'-]{0,48})$/i);
    if (singleWordMatch) {
      return [singleWordMatch[1].toLowerCase()];
    }
    return [];
  }

  function initDefinitionMatchState(exercise) {
    if (!exercise || exercise.exercise_type !== "word_definition_match") {
      setDefinitionMatchState({ words: [], definitions: [], mapping: {}, selectedWord: null, selectedDefinition: null });
      return;
    }
    const words = extractWordsFromDefinitionPrompt(exercise);
    const definitions = Array.isArray(exercise.options) ? exercise.options : [];
    const mapping = Object.fromEntries(words.map((word) => [word, ""]));
    setDefinitionMatchState({ words, definitions, mapping, selectedWord: null, selectedDefinition: null });
    setDefinitionLines([]);
    setCurrentAnswer("");
  }

  function updateDefinitionAnswer(mapping, words) {
    if (!words.length) {
      setCurrentAnswer("");
      return;
    }
    if (words.length === 1) {
      setCurrentAnswer(mapping[words[0]] || "");
      return;
    }
    const answerPayload = words.map((word) => ({ word, definition: mapping[word] || "" }));
    setCurrentAnswer(JSON.stringify(answerPayload));
  }

  function clearDefinitionPair(word) {
    setDefinitionMatchState((prev) => {
      const nextMapping = { ...prev.mapping, [word]: "" };
      updateDefinitionAnswer(nextMapping, prev.words);
      return { ...prev, mapping: nextMapping };
    });
  }

  function selectDefinitionWord(word) {
    setDefinitionMatchState((prev) => {
      if (!prev.words.length) {
        return prev;
      }
      if (prev.selectedWord === word) {
        return { ...prev, selectedWord: null };
      }
      if (prev.selectedDefinition) {
        const nextMapping = { ...prev.mapping, [word]: prev.selectedDefinition };
        updateDefinitionAnswer(nextMapping, prev.words);
        return { ...prev, mapping: nextMapping, selectedWord: null, selectedDefinition: null };
      }
      return { ...prev, selectedWord: word };
    });
  }

  function selectDefinitionOption(definition) {
    setDefinitionMatchState((prev) => {
      if (!prev.definitions.length) {
        return prev;
      }
      const usedByAnotherWord = Object.entries(prev.mapping).some(([word, value]) => value === definition && word !== prev.selectedWord);
      if (usedByAnotherWord) {
        return prev;
      }
      if (prev.selectedDefinition === definition) {
        return { ...prev, selectedDefinition: null };
      }
      if (prev.selectedWord) {
        const nextMapping = { ...prev.mapping, [prev.selectedWord]: definition };
        updateDefinitionAnswer(nextMapping, prev.words);
        return { ...prev, mapping: nextMapping, selectedWord: null, selectedDefinition: null };
      }
      if (prev.words.length === 1) {
        const onlyWord = prev.words[0];
        const nextMapping = { ...prev.mapping, [onlyWord]: definition };
        updateDefinitionAnswer(nextMapping, prev.words);
        return { ...prev, mapping: nextMapping, selectedWord: null, selectedDefinition: null };
      }
      return { ...prev, selectedDefinition: definition };
    });
  }

  useEffect(() => {
    if (!matchBoardRef.current || !definitionMatchState.words.length) {
      setDefinitionLines([]);
      return;
    }

    const recalc = () => {
      const boardRect = matchBoardRef.current.getBoundingClientRect();
      const nextLines = [];
      const wordIndexByName = Object.fromEntries(
        definitionMatchState.words.map((word, idx) => [word, idx]),
      );
      const definitionIndexByName = Object.fromEntries(
        definitionMatchState.definitions.map((definition, idx) => [definition, idx]),
      );
      const totalWords = Math.max(1, definitionMatchState.words.length);

      for (const word of definitionMatchState.words) {
        const definition = definitionMatchState.mapping[word];
        if (!definition) {
          continue;
        }
        const wordEl = wordRefs.current[word];
        const definitionEl = definitionRefs.current[definition];
        if (!wordEl || !definitionEl) {
          continue;
        }

        const wordRect = wordEl.getBoundingClientRect();
        const definitionRect = definitionEl.getBoundingClientRect();
        const radius = 9;
        const x1 = wordRect.right - boardRect.left;
        const y1 = wordRect.top - boardRect.top + wordRect.height / 2;
        const x2 = definitionRect.left - boardRect.left;
        const y2 = definitionRect.top - boardRect.top + definitionRect.height / 2;
        const corridorLeft = x1 + 14;
        const corridorRight = x2 - 14;
        const corridorWidth = Math.max(24, corridorRight - corridorLeft);
        const wordIdx = wordIndexByName[word] ?? 0;
        const defIdx = definitionIndexByName[definition] ?? 0;
        const laneBase = corridorLeft + (corridorWidth * (wordIdx + 1)) / (totalWords + 1);
        const laneBias = (wordIdx - defIdx) * 6;
        const middleX = Math.min(corridorRight, Math.max(corridorLeft, laneBase + laneBias));
        const dir = y2 >= y1 ? 1 : -1;
        const segment = Math.max(12, Math.min(36, Math.abs(y2 - y1) / 2));
        const r = Math.min(radius, segment, Math.max(0, (x2 - x1) / 4));

        const p1x = middleX - r;
        const p2x = middleX + r;
        const p1y = y1 + dir * r;
        const p2y = y2 - dir * r;
        const path = [
          `M ${x1} ${y1}`,
          `L ${p1x} ${y1}`,
          `Q ${middleX} ${y1} ${middleX} ${p1y}`,
          `L ${middleX} ${p2y}`,
          `Q ${middleX} ${y2} ${p2x} ${y2}`,
          `L ${x2} ${y2}`,
        ].join(" ");

        nextLines.push({
          key: `${word}=>${definition}`,
          path,
        });
      }
      setDefinitionLines(nextLines);
    };

    recalc();
    const onResize = () => recalc();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [definitionMatchState.mapping, definitionMatchState.words]);

  function pickLetter(letterId) {
    setScrambleState((prev) => {
      const letter = prev.available.find((item) => item.id === letterId);
      if (!letter) {
        return prev;
      }
      return {
        selected: [...prev.selected, letter],
        available: prev.available.filter((item) => item.id !== letterId),
      };
    });
  }

  function unpickLetter(letterId) {
    setScrambleState((prev) => {
      const letter = prev.selected.find((item) => item.id === letterId);
      if (!letter) {
        return prev;
      }
      return {
        selected: prev.selected.filter((item) => item.id !== letterId),
        available: [...prev.available, letter].sort((a, b) => a.originalIndex - b.originalIndex),
      };
    });
  }

  function resetPickedLetters() {
    setScrambleState((prev) => {
      if (!prev.selected.length) {
        return prev;
      }
      return {
        selected: [],
        available: [...prev.available, ...prev.selected].sort((a, b) => a.originalIndex - b.originalIndex),
      };
    });
  }

  async function generateBatch(targetMode, batchSize) {
    // 1. Dispatch task — returns immediately with task_id
    const { task_id } = await api.generateExercisesMe({ size: batchSize, mode: targetMode, vocabulary_ids: [] });
    // 2. Poll until the worker finishes
    const result = await pollTask(task_id, { intervalMs: 700, maxAttempts: 90 });
    if (!result || !result.exercises || result.exercises.length === 0) {
      throw new Error("Не удалось получить задание.");
    }
    return { exercises: result.exercises, note: result.note || "" };
  }

  function resetSessionState() {
    setCurrentExercise(null);
    setCurrentIndex(0);
    setCurrentAnswer("");
    setScrambleState({ selected: [], available: [] });
    setBufferExercises([]);
    setFetchedCount(0);
    setSubmittedAnswers([]);
    setSessionResult(null);
    setIsTrainingActive(false);
    setGenerationNote("");
  }

  async function startTraining() {
    setLoadingCurrent(true);
    onError("");
    try {
      const initialBatchSize = Math.min(PREFETCH_BATCH_SIZE, size);
      const { exercises: initialExercises, note } = await generateBatch(mode, initialBatchSize);
      setCurrentExercise(initialExercises[0]);
      setCurrentIndex(0);
      setCurrentAnswer("");
      initWordScrambleState(initialExercises[0], 0);
      initDefinitionMatchState(initialExercises[0]);
      setSubmittedAnswers([]);
      setBufferExercises(initialExercises.slice(1));
      setFetchedCount(initialExercises.length);
      setGenerationNote(note);
      setSessionResult(null);
      setIsTrainingActive(true);
    } catch (error) {
      onError(error.message.includes("Vocabulary is empty") ? "Словарь пуст. Сначала добавьте слова на странице словаря." : error.message);
    } finally {
      setLoadingCurrent(false);
    }
  }

  async function submitCurrentAndContinue() {
    if (!currentExercise) {
      return;
    }

    const effectiveAnswer =
      currentExercise.exercise_type === "word_scramble"
        ? selectedLetters.map((item) => item.char).join("")
        : currentAnswer;

    const nextAnswers = [
      ...submittedAnswers,
      {
        exercise_id: currentIndex + 1,
        prompt: currentExercise.prompt,
        expected_answer: currentExercise.answer,
        user_answer: (effectiveAnswer || "-").trim() || "-",
        is_correct: false,
      },
    ];
    setSubmittedAnswers(nextAnswers);

    const nextIndex = currentIndex + 1;
    if (nextIndex >= size) {
      await submitSession(nextAnswers);
      setIsTrainingActive(false);
      setCurrentExercise(null);
      setBufferExercises([]);
      return;
    }

    if (bufferExercises.length > 0) {
      const [nextExercise, ...rest] = bufferExercises;
      setCurrentExercise(nextExercise);
      setBufferExercises(rest);
      setCurrentIndex(nextIndex);
      setCurrentAnswer("");
      initWordScrambleState(nextExercise, nextIndex);
      initDefinitionMatchState(nextExercise);
      return;
    }

    setLoadingCurrent(true);
    try {
      const remaining = size - fetchedCount;
      const batchSize = Math.max(1, Math.min(PREFETCH_BATCH_SIZE, remaining));
      const { exercises: generatedBatch, note } = await generateBatch(mode, batchSize);
      const [nextExercise, ...rest] = generatedBatch;
      setCurrentExercise(nextExercise);
      setBufferExercises(rest);
      setFetchedCount((prev) => prev + generatedBatch.length);
      setCurrentIndex(nextIndex);
      setCurrentAnswer("");
      setGenerationNote(note);
      initWordScrambleState(nextExercise, nextIndex);
      initDefinitionMatchState(nextExercise);
    } catch (error) {
      onError(error.message);
    } finally {
      setLoadingCurrent(false);
    }
  }

  async function submitSession(answersPayload) {
    try {
      const result = await api.submitSession({ answers: answersPayload });
      setSessionResult(result);
    } catch (error) {
      onError(error.message);
    }
  }

  useEffect(() => {
    if (!isTrainingActive || loadingCurrent || loadingPrefetch) {
      return;
    }

    const remaining = size - fetchedCount;
    if (remaining <= 0 || bufferExercises.length >= PREFETCH_BATCH_SIZE) {
      return;
    }

    let cancelled = false;
    setLoadingPrefetch(true);
    const batchSize = Math.min(PREFETCH_BATCH_SIZE, remaining);
    generateBatch(mode, batchSize)
      .then(({ exercises: batch, note }) => {
        if (cancelled) {
          return;
        }
        setBufferExercises((prev) => [...prev, ...batch]);
        setFetchedCount((prev) => prev + batch.length);
        if (note) {
          setGenerationNote(note);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          onError(error.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingPrefetch(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isTrainingActive, loadingCurrent, loadingPrefetch, size, fetchedCount, bufferExercises.length, mode, onError]);

  const answerReady = useMemo(() => {
    if (!currentExercise) {
      return false;
    }
    if (currentExercise.exercise_type === "word_scramble") {
      return selectedLetters.length > 0;
    }
    if (currentExercise.exercise_type === "word_definition_match") {
      const words = definitionMatchState.words;
      if (!words.length) {
        return false;
      }
      return words.every((word) => (definitionMatchState.mapping[word] || "").trim().length > 0);
    }
    return currentAnswer.trim().length > 0;
  }, [currentExercise, selectedLetters, currentAnswer, definitionMatchState]);

  return (
    <section className="space-y-4">
      {loadingCurrent && <LoadingSpinner message="Генерирую упражнения..." estimatedSeconds="3-8" />}

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
              onChange={(e) => setSize(Number(e.target.value || 1))}
              className="field mt-1"
              disabled={isTrainingActive}
            />
          </label>
          <label className="text-sm md:col-span-2">
            Тип упражнений
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
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

          {currentExercise.exercise_type === "word_scramble" ? (
            <div className="mt-3 space-y-3">
              <div className="surface-strong p-3 text-sm">
                Собранное слово: <span className="font-extrabold text-gray-900">{selectedLetters.map((item) => item.char).join("") || "—"}</span>
              </div>

              <div className="rounded-xl border-2 border-dashed border-gray-300 bg-white px-3 py-2 text-sm">
                <p className="muted mb-2 text-xs">Собираем слово (клик по букве возвращает её обратно)</p>
                <div className="flex min-h-10 flex-wrap gap-2">
                  {selectedLetters.length ? (
                    selectedLetters.map((letter) => (
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
                  {availableLetters.length ? (
                    availableLetters.map((letter) => (
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
          ) : currentExercise.exercise_type === "word_definition_match" ? (
            <div className="mt-3 space-y-4">
              <div ref={matchBoardRef} className="relative">
                {definitionLines.length > 0 ? (
                  <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true">
                    {definitionLines.map((line) => (
                      <path
                        key={line.key}
                        d={line.path}
                        stroke="#3B82F6"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        fill="none"
                      />
                    ))}
                  </svg>
                ) : null}
                <div className="relative z-20 grid gap-8 lg:grid-cols-2 lg:gap-12">
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-gray-900">Слова</p>
                  {definitionMatchState.words.map((word) => {
                    const mappedDefinition = definitionMatchState.mapping[word];
                    const isSelected = definitionMatchState.selectedWord === word;
                    return (
                      <div key={`${currentIndex}-word-${word}`} className="relative">
                        <button
                          ref={(el) => {
                            if (el) {
                              wordRefs.current[word] = el;
                            }
                          }}
                          type="button"
                          onClick={() => selectDefinitionWord(word)}
                          className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${
                            isSelected
                              ? "border-blue-600 bg-blue-600 text-white"
                              : mappedDefinition
                                ? "border-blue-300 bg-blue-50 text-blue-800"
                                : "border-[var(--line)] bg-white hover:bg-blue-50"
                          }`}
                        >
                          <span className="font-semibold">{word}</span>
                        </button>
                        {mappedDefinition ? (
                          <button
                            type="button"
                            onClick={() => clearDefinitionPair(word)}
                            className="absolute right-2 top-2 rounded px-1 text-xs text-red-600 hover:bg-red-50"
                            aria-label={`Удалить сопоставление для ${word}`}
                          >
                            x
                          </button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-gray-900">Определения</p>
                  {definitionMatchState.definitions.map((definition) => {
                    const isSelected = definitionMatchState.selectedDefinition === definition;
                    const isUsed = Object.values(definitionMatchState.mapping).includes(definition);
                    return (
                      <button
                        ref={(el) => {
                          if (el) {
                            definitionRefs.current[definition] = el;
                          }
                        }}
                        key={`${currentIndex}-def-${definition}`}
                        type="button"
                        onClick={() => selectDefinitionOption(definition)}
                        className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${
                          isSelected
                            ? "border-blue-600 bg-blue-600 text-white"
                            : isUsed
                              ? "border-blue-300 bg-blue-50 text-blue-800"
                              : "border-[var(--line)] bg-white hover:bg-blue-50"
                        }`}
                      >
                        {definition}
                      </button>
                    );
                  })}
                </div>
              </div>
              </div>
              <div className="surface-strong p-3 text-sm">
                {definitionMatchState.selectedWord && !definitionMatchState.selectedDefinition ? (
                  <>Выбрано слово: <span className="font-semibold">{definitionMatchState.selectedWord}</span>. Теперь выберите определение.</>
                ) : null}
                {definitionMatchState.selectedDefinition && !definitionMatchState.selectedWord ? (
                  <>Выбрано определение. Теперь выберите слово.</>
                ) : null}
                {!definitionMatchState.selectedWord && !definitionMatchState.selectedDefinition ? (
                  <>Нажмите на слово и определение, чтобы создать сопоставление.</>
                ) : null}
              </div>
            </div>
          ) : currentExercise.options && currentExercise.options.length > 1 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {currentExercise.options.map((option) => {
                const selected = currentAnswer === option;
                return (
                  <button
                    key={`${currentIndex}-${option}`}
                    type="button"
                    onClick={() => setCurrentAnswer(option)}
                    className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${
                      selected ? "border-blue-600 bg-blue-600 text-white" : "border-[var(--line)] bg-white hover:bg-blue-50"
                    }`}
                  >
                    {option}
                  </button>
                );
              })}
            </div>
          ) : (
            <textarea
              className="field mt-3"
              rows={4}
              placeholder="Введите перевод..."
              value={currentAnswer}
              onChange={(e) => setCurrentAnswer(e.target.value)}
            />
          )}

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
