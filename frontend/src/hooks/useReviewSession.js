import { useEffect, useMemo, useState } from "react";
import { api, getErrorMessage, isAbortError } from "../lib/api";
import { useAbortControllers } from "./useAbortControllers";

const FLIP_ANIMATION_MS = 520;

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function useReviewSession({ onError }) {
  const [plan, setPlan] = useState(null);
  const [summary, setSummary] = useState(null);
  const [graphRecommendations, setGraphRecommendations] = useState([]);
  const [graphAnchorsByLemma, setGraphAnchorsByLemma] = useState({});
  const [sessionSize, setSessionSize] = useState(20);
  const [sessionMode, setSessionMode] = useState(null);
  const [sessionItems, setSessionItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [sessionCorrect, setSessionCorrect] = useState(0);
  const [sessionIncorrect, setSessionIncorrect] = useState(0);
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sessionMessage, setSessionMessage] = useState("");
  const { abortAllRequests, registerController, releaseController } = useAbortControllers();

  async function loadReviewMeta() {
    const controller = registerController();
    try {
      const [planData, summaryData, graphData] = await Promise.all([
        api.reviewPlan(10, { signal: controller.signal }),
        api.reviewSummary({ signal: controller.signal }),
        api.learningGraphRecommendations("mixed", 5, { signal: controller.signal }),
      ]);
      setPlan(planData);
      setSummary(summaryData);
      const items = graphData?.items || [];
      setGraphRecommendations(items);

      const topForAnchors = items.slice(0, 3);
      if (!topForAnchors.length) {
        setGraphAnchorsByLemma({});
        return;
      }
      const anchorResults = await Promise.allSettled(
        topForAnchors.map((item) => api.learningGraphAnchors(item.english_lemma, 3, { signal: controller.signal })),
      );
      const anchorsMap = {};
      topForAnchors.forEach((item, index) => {
        const result = anchorResults[index];
        if (result.status === "fulfilled") {
          anchorsMap[item.english_lemma] = result.value?.anchors || [];
        }
      });
      setGraphAnchorsByLemma(anchorsMap);
    } catch (error) {
      if (!isAbortError(error)) {
        onError(getErrorMessage(error));
      }
    } finally {
      releaseController(controller);
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
    const controller = registerController();
    try {
      const data = await api.reviewStartSession({ mode, size: sessionSize }, { signal: controller.signal });
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
      if (!isAbortError(error)) {
        onError(getErrorMessage(error));
      }
    } finally {
      releaseController(controller);
      setStarting(false);
    }
  }

  async function submitAnswer(isCorrect) {
    if (!currentItem || submitting) {
      return;
    }
    setSubmitting(true);
    onError("");
    const controller = registerController();
    try {
      const submitPromise =
        sessionMode === "srs"
          ? api.reviewQueueSubmit({ word: currentItem.word, is_correct: isCorrect }, { signal: controller.signal })
          : Promise.resolve();

      setIsFlipped(false);
      await Promise.all([submitPromise, wait(FLIP_ANIMATION_MS)]);

      if (isCorrect) {
        setSessionCorrect((prev) => prev + 1);
      } else {
        setSessionIncorrect((prev) => prev + 1);
      }
      setCurrentIndex((prev) => prev + 1);
    } catch (error) {
      if (!isAbortError(error)) {
        onError(getErrorMessage(error));
      }
    } finally {
      releaseController(controller);
      setSubmitting(false);
    }
  }

  function resetSession() {
    abortAllRequests();
    setSessionMode(null);
    setSessionItems([]);
    setCurrentIndex(0);
    setIsFlipped(false);
    setSessionCorrect(0);
    setSessionIncorrect(0);
    setSessionMessage("");
  }

  return {
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
  };
}
