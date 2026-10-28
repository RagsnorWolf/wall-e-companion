import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar } from "./components/shell/Sidebar";
import { TopBar } from "./components/shell/TopBar";
import { DashboardView } from "./views/DashboardView";
import { ControlView } from "./views/ControlView";
import { VisionView } from "./views/VisionView";
import { MemoryView } from "./views/MemoryView";
import { AgendaView } from "./views/AgendaView";
import { SettingsView } from "./views/SettingsView";
import { useRobot } from "./hooks/useRobot";
import { useToast } from "./hooks/useToasts";
import { api } from "./lib/api";
import { shortClock, uptime } from "./lib/format";

const WELCOME = {
  id: "boot",
  role: "system",
  text: "Núcleo local en línea. WALL·E está despierto y mirando la planta.",
  time: shortClock(),
};

export function App() {
  const { state, events, online, refresh, setState } = useRobot(2400);
  const notify = useToast();

  const [view, setView] = useState("dashboard");
  const [messages, setMessages] = useState([WELCOME]);
  const [thinking, setThinking] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [latency, setLatency] = useState(null);
  const [sound, setSound] = useState(() => {
    try {
      return localStorage.getItem("walle.sound") !== "off";
    } catch {
      return true;
    }
  });
  const [history, setHistory] = useState([]);
  const [camera, setCamera] = useState(null);
  const [cameraLive, setCameraLive] = useState(false);
  const [color, setColor] = useState("rojo");
  const [ports, setPorts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [chatSeed, setChatSeed] = useState(null);

  const thinkingRef = useRef(false);
  const soundRef = useRef(sound);
  const cameraWarned = useRef(false);

  useEffect(() => {
    soundRef.current = sound;
    try {
      localStorage.setItem("walle.sound", sound ? "on" : "off");
    } catch {
      /* almacenamiento bloqueado */
    }
  }, [sound]);

  useEffect(() => {
    if (state?.system?.cpu == null) return;
    setHistory((current) => [...current.slice(-27), Number(state.system.cpu)]);
  }, [state?.system?.cpu]);

  const loadPorts = useCallback(async () => {
    try {
      const data = await api.ports();
      setPorts(data.ports || []);
    } catch {
      setPorts([]);
    }
  }, []);

  useEffect(() => {
    loadPorts();
  }, [loadPorts]);

  const speak = useCallback((text) => {
    if (!soundRef.current || !("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-AR";
    utterance.rate = 1.03;
    utterance.pitch = 1.12;
    const voices = synth.getVoices();
    const voice =
      voices.find((item) => /es[-_]AR/i.test(item.lang)) ||
      voices.find((item) => /es[-_]MX/i.test(item.lang)) ||
      voices.find((item) => item.lang?.toLowerCase().startsWith("es"));
    if (voice) utterance.voice = voice;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    synth.speak(utterance);
  }, []);

  const send = useCallback(
    async (text) => {
      const clean = (text || "").trim();
      if (!clean || thinkingRef.current) return;
      thinkingRef.current = true;
      setThinking(true);
      setMessages((current) => [
        ...current,
        { id: `u-${Date.now()}`, role: "user", text: clean, time: shortClock() },
      ]);

      try {
        const data = await api.chat(clean);
        const reply = data.reply || "Mmm. No sé qué decir.";
        setMessages((current) => [
          ...current,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            text: reply,
            time: shortClock(),
            seconds: data.seconds,
          },
        ]);
        setLatency(data.seconds ?? null);
        if (data.state) setState(data.state);
        speak(reply);
      } catch (error) {
        setMessages((current) => [
          ...current,
          {
            id: `e-${Date.now()}`,
            role: "assistant",
            error: true,
            text: `No pude responder: ${error.message}`,
            time: shortClock(),
          },
        ]);
        notify(error.message, "error");
      } finally {
        thinkingRef.current = false;
        setThinking(false);
        refresh();
      }
    },
    [notify, refresh, setState, speak]
  );

  const run = useCallback(
    async (action, successMessage) => {
      setBusy(true);
      try {
        const data = await action();
        if (data?.state) setState(data.state);
        if (successMessage) notify(successMessage, "success");
        return data;
      } catch (error) {
        notify(error.message, "error");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [notify, setState]
  );

  const handleDrive = useCallback(
    async (left, right) => {
      try {
        await api.drive(left, right);
      } catch (error) {
        notify(error.message, "error");
      }
    },
    [notify]
  );

  const handleMove = useCallback(
    async (left, right, seconds) => {
      setBusy(true);
      try {
        const data = await api.move(left, right, seconds);
        if (data.state) setState(data.state);
      } catch (error) {
        notify(error.message, "error");
      } finally {
        setBusy(false);
      }
    },
    [notify, setState]
  );

  const handleStop = useCallback(async () => {
    try {
      const data = await api.stop();
      if (data.state) setState(data.state);
      notify("Parada de emergencia enviada.", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify, setState]);

  const handleConnect = useCallback(
    async (port) => {
      if (!port) {
        notify("Elegí un puerto primero.", "error");
        return;
      }
      await run(() => api.connect(port), `Enlace abierto en ${port}.`);
      loadPorts();
    },
    [loadPorts, notify, run]
  );

  const handleDisconnect = useCallback(async () => {
    await run(() => api.disconnect(), "Cuerpo desconectado.");
  }, [run]);

  const handlePet = useCallback(async () => {
    try {
      const data = await api.emotion("caricia");
      if (data.state) setState(data.state);
      else refresh();
      notify("WALL·E se puso contento.", "success");
      if (soundRef.current && "speechSynthesis" in window) {
        const synth = window.speechSynthesis;
        synth.cancel();
        const utterance = new SpeechSynthesisUtterance("¡Ay! Qué lindo.");
        utterance.lang = "es-AR";
        utterance.pitch = 1.25;
        utterance.rate = 1.05;
        utterance.onstart = () => setSpeaking(true);
        utterance.onend = () => setSpeaking(false);
        synth.speak(utterance);
      }
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify, refresh, setState]);

  const handleTracking = useCallback(
    async (enabled) => {
      await run(
        () => api.track(enabled, color),
        enabled ? `Seguimiento de ${color} activado.` : "Seguimiento desactivado."
      );
    },
    [color, run]
  );

  const handleColor = useCallback(
    async (next) => {
      setColor(next);
      if (state?.tracking?.enabled) {
        await run(
          () => api.track(true, next),
          `Objetivo cambiado a ${next}.`
        );
      }
    },
    [run, state?.tracking?.enabled]
  );

  const fetchFrame = useCallback(async () => {
    const data = await api.camera(color);
    setCamera(data);
    cameraWarned.current = false;
    return data;
  }, [color]);

  useEffect(() => {
    if (!cameraLive) return undefined;
    let cancelled = false;
    let timer = null;

    const tick = async () => {
      try {
        const data = await api.camera(color);
        if (cancelled) return;
        setCamera(data);
        cameraWarned.current = false;
      } catch (error) {
        if (cancelled) return;
        setCameraLive(false);
        if (!cameraWarned.current) {
          cameraWarned.current = true;
          notify(error.message, "error");
        }
      } finally {
        if (!cancelled) timer = window.setTimeout(tick, 1000);
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [cameraLive, color, notify]);

  const handleCapture = useCallback(async () => {
    try {
      await fetchFrame();
      notify("Cuadro capturado.", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [fetchFrame, notify]);

  const handleLive = useCallback(() => {
    setCameraLive((current) => !current);
  }, []);

  const handleChatSeed = useCallback((text) => {
    setChatSeed(text);
    setView("dashboard");
    window.setTimeout(() => {
      document.querySelector(".chat-composer textarea")?.focus();
    }, 220);
  }, []);

  const handleSeedUsed = useCallback(() => setChatSeed(null), []);

  const mood = state?.emotion?.mood || "tranquilo";

  const shared = useMemo(
    () => ({
      state,
      events,
      history,
      messages,
      thinking,
      speaking,
      latency,
      sound,
      camera,
      color,
      cameraLive,
      ports,
      busy,
      mood,
      onSound: () => setSound((current) => !current),
      onSend: send,
      onDrive: handleDrive,
      onMove: handleMove,
      onStop: handleStop,
      onConnect: handleConnect,
      onDisconnect: handleDisconnect,
      onRefreshPorts: loadPorts,
      onPet: handlePet,
      onTracking: handleTracking,
      onColor: handleColor,
      onCapture: handleCapture,
      onLive: handleLive,
      onChatSeed: handleChatSeed,
      onSeedUsed: handleSeedUsed,
      notify,
      refresh,
    }),
    [
      state,
      events,
      history,
      messages,
      thinking,
      speaking,
      latency,
      sound,
      camera,
      color,
      cameraLive,
      ports,
      busy,
      mood,
      send,
      handleDrive,
      handleMove,
      handleStop,
      handleConnect,
      handleDisconnect,
      loadPorts,
      handlePet,
      handleTracking,
      handleColor,
      handleCapture,
      handleLive,
      handleChatSeed,
      handleSeedUsed,
      notify,
      refresh,
    ]
  );

  return (
    <div className="app-shell">
      <div className="app-noise" aria-hidden="true" />
      <Sidebar view={view} onView={setView} state={state} online={online} />

      <div className="app-main">
        <TopBar
          view={view}
          state={state}
          online={online}
          sound={sound}
          onSound={() => setSound((current) => !current)}
        />

        <main className="app-view">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={view}
              className="view"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              {view === "dashboard" ? (
                <DashboardView
                  {...shared}
                  chatSeed={chatSeed}
                  onSeedUsed={handleSeedUsed}
                />
              ) : null}
              {view === "control" ? <ControlView {...shared} /> : null}
              {view === "vision" ? <VisionView {...shared} /> : null}
              {view === "memory" ? <MemoryView {...shared} /> : null}
              {view === "agenda" ? <AgendaView {...shared} /> : null}
              {view === "settings" ? <SettingsView {...shared} /> : null}
            </motion.div>
          </AnimatePresence>
        </main>

        <footer className="status-bar">
          <span className={`status-bar__dot ${online ? "is-ok" : "is-bad"}`} />
          <span>{online ? "ENLACE LOCAL 127.0.0.1:8765" : "SIN CONEXIÓN CON EL SERVIDOR"}</span>
          <i />
          <span>MODELO {state?.model?.toUpperCase() || "WALL·E"}</span>
          <i />
          <span>{state?.connected ? `SERIAL ${state.port}` : "CUERPO EN SIMULACIÓN"}</span>
          <i />
          <span>{state?.ollama ? "OLLAMA OK" : "OLLAMA SIN RESPUESTA"}</span>
          <span className="status-bar__spacer" />
          <span>{latency ? `ÚLTIMA RESPUESTA ${latency}s` : "SIN TURNOS"}</span>
          <i />
          <span>UPTIME {uptime(state?.uptime)}</span>
          <i />
          <span className="status-bar__build">BUILD 026 · v{state?.version || "2.0"}</span>
        </footer>
      </div>
    </div>
  );
}
