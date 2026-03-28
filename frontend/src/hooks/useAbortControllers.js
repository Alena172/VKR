import { useCallback, useEffect, useRef } from "react";

export function useAbortControllers() {
  const controllersRef = useRef(new Set());

  const registerController = useCallback(() => {
    const controller = new AbortController();
    controllersRef.current.add(controller);
    return controller;
  }, []);

  const releaseController = useCallback((controller) => {
    controllersRef.current.delete(controller);
  }, []);

  const abortAllRequests = useCallback(() => {
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
  }, []);

  useEffect(() => {
    return () => {
      abortAllRequests();
    };
  }, [abortAllRequests]);

  return {
    abortAllRequests,
    registerController,
    releaseController,
  };
}
