import { useEffect, useRef, useState } from "react";

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

function buildAnswerPayload(mapping, words) {
  if (!words.length) {
    return "";
  }
  if (words.length === 1) {
    return mapping[words[0]] || "";
  }
  return JSON.stringify(words.map((word) => ({ word, definition: mapping[word] || "" })));
}

export default function DefinitionMatchExercise({ exercise, exercisePosition, onAnswerChange }) {
  const [words, setWords] = useState([]);
  const [definitions, setDefinitions] = useState([]);
  const [mapping, setMapping] = useState({});
  const [selectedWord, setSelectedWord] = useState(null);
  const [selectedDefinition, setSelectedDefinition] = useState(null);
  const [definitionLines, setDefinitionLines] = useState([]);
  const matchBoardRef = useRef(null);
  const wordRefs = useRef({});
  const definitionRefs = useRef({});

  useEffect(() => {
    if (!exercise || exercise.exercise_type !== "word_definition_match") {
      setWords([]);
      setDefinitions([]);
      setMapping({});
      setSelectedWord(null);
      setSelectedDefinition(null);
      setDefinitionLines([]);
      wordRefs.current = {};
      definitionRefs.current = {};
      onAnswerChange("");
      return;
    }

    const nextWords = extractWordsFromDefinitionPrompt(exercise);
    const nextDefinitions = Array.isArray(exercise.options) ? exercise.options : [];
    const nextMapping = Object.fromEntries(nextWords.map((word) => [word, ""]));
    setWords(nextWords);
    setDefinitions(nextDefinitions);
    setMapping(nextMapping);
    setSelectedWord(null);
    setSelectedDefinition(null);
    setDefinitionLines([]);
    wordRefs.current = {};
    definitionRefs.current = {};
    onAnswerChange("");
  }, [exercise, onAnswerChange]);

  useEffect(() => {
    onAnswerChange(buildAnswerPayload(mapping, words));
  }, [mapping, onAnswerChange, words]);

  useEffect(() => {
    if (!matchBoardRef.current || !words.length) {
      setDefinitionLines([]);
      return undefined;
    }

    const recalc = () => {
      if (!matchBoardRef.current) {
        return;
      }
      const boardRect = matchBoardRef.current.getBoundingClientRect();
      const nextLines = [];
      const wordIndexByName = Object.fromEntries(words.map((word, idx) => [word, idx]));
      const definitionIndexByName = Object.fromEntries(definitions.map((definition, idx) => [definition, idx]));
      const totalWords = Math.max(1, words.length);

      for (const word of words) {
        const definition = mapping[word];
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
    window.addEventListener("resize", recalc);
    return () => window.removeEventListener("resize", recalc);
  }, [definitions, mapping, words, exercisePosition]);

  function clearDefinitionPair(word) {
    setMapping((prev) => ({ ...prev, [word]: "" }));
  }

  function selectDefinitionWord(word) {
    if (!words.length) {
      return;
    }
    if (selectedWord === word) {
      setSelectedWord(null);
      return;
    }
    if (selectedDefinition) {
      setMapping((prev) => ({ ...prev, [word]: selectedDefinition }));
      setSelectedWord(null);
      setSelectedDefinition(null);
      return;
    }
    setSelectedWord(word);
  }

  function selectDefinitionOption(definition) {
    if (!definitions.length) {
      return;
    }
    const usedByAnotherWord = Object.entries(mapping).some(([word, value]) => value === definition && word !== selectedWord);
    if (usedByAnotherWord) {
      return;
    }
    if (selectedDefinition === definition) {
      setSelectedDefinition(null);
      return;
    }
    if (selectedWord) {
      setMapping((prev) => ({ ...prev, [selectedWord]: definition }));
      setSelectedWord(null);
      setSelectedDefinition(null);
      return;
    }
    if (words.length === 1) {
      setMapping((prev) => ({ ...prev, [words[0]]: definition }));
      return;
    }
    setSelectedDefinition(definition);
  }

  return (
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
            {words.map((word) => {
              const mappedDefinition = mapping[word];
              const isSelected = selectedWord === word;
              return (
                <div key={`${exercisePosition}-word-${word}`} className="relative">
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
            {definitions.map((definition) => {
              const isSelected = selectedDefinition === definition;
              const isUsed = Object.values(mapping).includes(definition);
              return (
                <button
                  ref={(el) => {
                    if (el) {
                      definitionRefs.current[definition] = el;
                    }
                  }}
                  key={`${exercisePosition}-def-${definition}`}
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
        {selectedWord && !selectedDefinition ? (
          <>Выбрано слово: <span className="font-semibold">{selectedWord}</span>. Теперь выберите определение.</>
        ) : null}
        {selectedDefinition && !selectedWord ? <>Выбрано определение. Теперь выберите слово.</> : null}
        {!selectedWord && !selectedDefinition ? <>Нажмите на слово и определение, чтобы создать сопоставление.</> : null}
      </div>
    </div>
  );
}
