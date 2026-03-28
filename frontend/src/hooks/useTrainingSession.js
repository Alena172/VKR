import { useEffect, useMemo, useRef, useState } from "react";
import { api, getErrorMessage, isAbortError, pollTask } from "../lib/api";

const PREFETCH_BATCH_SIZE = 2;

export function useTrainingSession({ onError }) {
  const [size, setSize] = useState(6);
  const [mode, setMode] = useState("sentence_translation_full");
  const [currentExercise, setCurrentExercise] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [currentAnswer, setCurrentAnswer] = useState("");
  const [bufferExercises, setBufferExercises] = useState([]);
  const [fetchedCount, setFetchedCount] = useState(0);
  const [submittedAnswers, setSubmittedAnswers] = useState([]);
  const [loadingCurrent, setLoadingCurrent] = useState(false);
  const [loadingPrefetch, setLoadingPrefetch] = useState(false);
  const [sessionResult, setSessionResult] = useState(null);
  const [isTrainingActive, setIsTrainingActive] = useState(false);
  const [generationNote, setGenerationNote] = useState("");
  const controllersRef = useRef(new Set());

  const progressPercent = size > 0 ? Math.round((currentIndex / size) * 100) : 0;

  function registerController() {
    const controller = new AbortController();
    controllersRef.current.add(controller);
    return controller;
  }

  function releaseController(controller) {
    controllersRef.current.delete(controller);
  }

  function abortAllRequests() {
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
  }

  async function generateBatch(targetMode, batchSize, signal) {
    const { task_id } = await api.generateExercisesMe(
      { size: batchSize, mode: targetMode, vocabulary_ids: [] },
      { signal },
    );
    const result = await pollTask(task_id, {
      intervalMs: 700,
      maxAttempts: 90,
      maxIntervalMs: 3000,
      backoffFactor: 1.4,
      signal,
    });
    if (!result || !result.exercises || result.exercises.length === 0) {
      throw new Error("Не удалось получить задание.");
    }
    return { exercises: result.exercises, note: result.note || "" };
  }

  function resetSessionState() {
    abortAllRequests();
    setCurrentExercise(null);
    setCurrentIndex(0);
    setCurrentAnswer("");
    setBufferExercises([]);
    setFetchedCount(0);
    setSubmittedAnswers([]);
    setSessionResult(null);
    setIsTrainingActive(false);
    setGenerationNote("");
    setLoadingCurrent(false);
    setLoadingPrefetch(false);
  }

  async function submitSession(answersPayload, signal) {
    const result = await api.submitSession({ answers: answersPayload }, { signal });
    setSessionResult(result);
  }

  async function startTraining() {
    abortAllRequests();
    setLoadingCurrent(true);
    onError("");
    try {
      const initialBatchSize = Math.min(PREFETCH_BATCH_SIZE, size);
      const controller = registerController();
      try {
        const { exercises: initialExercises, note } = await generateBatch(mode, initialBatchSize, controller.signal);
        setCurrentExercise(initialExercises[0]);
        setCurrentIndex(0);
        setCurrentAnswer("");
        setSubmittedAnswers([]);
        setBufferExercises(initialExercises.slice(1));
        setFetchedCount(initialExercises.length);
        setGenerationNote(note);
        setSessionResult(null);
        setIsTrainingActive(true);
      } finally {
        releaseController(controller);
      }
    } catch (error) {
      if (!isAbortError(error)) {
        onError(
          getErrorMessage(error).includes("Vocabulary is empty")
            ? "Словарь пуст. Сначала добавьте слова на странице словаря."
            : getErrorMessage(error),
        );
      }
    } finally {
      setLoadingCurrent(false);
    }
  }

  async function submitCurrentAndContinue() {
    if (!currentExercise) {
      return;
    }

    const nextAnswers = [
      ...submittedAnswers,
      {
        exercise_id: currentIndex + 1,
        prompt: currentExercise.prompt,
        expected_answer: currentExercise.answer,
        user_answer: (currentAnswer || "-").trim() || "-",
        is_correct: false,
      },
    ];
    setSubmittedAnswers(nextAnswers);

    const nextIndex = currentIndex + 1;
    if (nextIndex >= size) {
      const controller = registerController();
      try {
        await submitSession(nextAnswers, controller.signal);
        setIsTrainingActive(false);
        setCurrentExercise(null);
        setBufferExercises([]);
      } catch (error) {
        if (!isAbortError(error)) {
          onError(getErrorMessage(error));
        }
      } finally {
        releaseController(controller);
      }
      return;
    }

    if (bufferExercises.length > 0) {
      const [nextExercise, ...rest] = bufferExercises;
      setCurrentExercise(nextExercise);
      setBufferExercises(rest);
      setCurrentIndex(nextIndex);
      setCurrentAnswer("");
      return;
    }

    setLoadingCurrent(true);
    try {
      const remaining = size - fetchedCount;
      const batchSize = Math.max(1, Math.min(PREFETCH_BATCH_SIZE, remaining));
      const controller = registerController();
      try {
        const { exercises: generatedBatch, note } = await generateBatch(mode, batchSize, controller.signal);
        const [nextExercise, ...rest] = generatedBatch;
        setCurrentExercise(nextExercise);
        setBufferExercises(rest);
        setFetchedCount((prev) => prev + generatedBatch.length);
        setCurrentIndex(nextIndex);
        setCurrentAnswer("");
        setGenerationNote(note);
      } finally {
        releaseController(controller);
      }
    } catch (error) {
      if (!isAbortError(error)) {
        onError(getErrorMessage(error));
      }
    } finally {
      setLoadingCurrent(false);
    }
  }

  useEffect(() => {
    if (!isTrainingActive || loadingCurrent || loadingPrefetch) {
      return undefined;
    }

    const remaining = size - fetchedCount;
    if (remaining <= 0 || bufferExercises.length >= PREFETCH_BATCH_SIZE) {
      return undefined;
    }

    const controller = registerController();
    setLoadingPrefetch(true);
    const batchSize = Math.min(PREFETCH_BATCH_SIZE, remaining);

    generateBatch(mode, batchSize, controller.signal)
      .then(({ exercises: batch, note }) => {
        setBufferExercises((prev) => [...prev, ...batch]);
        setFetchedCount((prev) => prev + batch.length);
        if (note) {
          setGenerationNote(note);
        }
      })
      .catch((error) => {
        if (!isAbortError(error)) {
          onError(getErrorMessage(error));
        }
      })
      .finally(() => {
        releaseController(controller);
        setLoadingPrefetch(false);
      });

    return () => {
      controller.abort();
      releaseController(controller);
    };
  }, [bufferExercises.length, fetchedCount, isTrainingActive, loadingCurrent, mode, onError, size]);

  useEffect(() => {
    return () => {
      abortAllRequests();
    };
  }, []);

  const answerReady = useMemo(() => {
    if (!currentExercise) {
      return false;
    }
    return currentAnswer.trim().length > 0;
  }, [currentAnswer, currentExercise]);

  return {
    answerReady,
    bufferExercises,
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
  };
}
