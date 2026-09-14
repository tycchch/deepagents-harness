import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export function useAppHistory() {
  const navigate = useNavigate();
  const location = useLocation();
  const key = `${location.pathname}${location.search}`;
  const hist = useRef({ stack: [] as string[], index: -1 });
  const [, stamp] = useState(0);

  useEffect(() => {
    const state = hist.current;
    if (state.stack[state.index] === key) return;
    if (state.index > 0 && state.stack[state.index - 1] === key) {
      state.index -= 1;
    } else if (state.index >= 0 && state.stack[state.index + 1] === key) {
      state.index += 1;
    } else {
      state.stack = [...state.stack.slice(0, state.index + 1), key];
      state.index = state.stack.length - 1;
    }
    stamp((n) => n + 1);
  }, [key]);

  return {
    canBack: hist.current.index > 0,
    canForward: hist.current.index >= 0 && hist.current.index < hist.current.stack.length - 1,
    back() {
      if (hist.current.index <= 0) return;
      navigate(-1);
    },
    forward() {
      if (hist.current.index >= hist.current.stack.length - 1) return;
      navigate(1);
    },
  };
}
