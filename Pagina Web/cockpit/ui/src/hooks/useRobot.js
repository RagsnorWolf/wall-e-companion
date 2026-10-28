import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

export function useRobot(pollMs = 2500) {
  const [state, setState] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [online, setOnline] = useState(true);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const [nextState, nextEvents] = await Promise.all([
        api.state(),
        api.events(36),
      ]);
      if (!alive.current) return;
      setState(nextState);
      setEvents(nextEvents.events || []);
      setError(null);
      setOnline(true);
    } catch (err) {
      if (!alive.current) return;
      setError(err.message);
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    refresh();
    const timer = window.setInterval(refresh, pollMs);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [refresh, pollMs]);

  return { state, events, error, online, refresh, setState };
}
