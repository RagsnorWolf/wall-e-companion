import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CornerDownLeft,
  Mic,
  MicOff,
  Radio,
  Send,
  Sparkles,
  Terminal,
  Volume2,
  VolumeX,
} from "lucide-react";
import { Panel } from "../ui/Panel";
import { shortClock } from "../../lib/format";

const QUICK = [
  "¿Quién sos?",
  "¿Cómo estás?",
  "¿Qué ves?",
  "¿Qué hora es?",
  "Acordate que me llamo Gonzalo",
  "Abrí el bloc de notas",
];

export function ChatPanel({
  messages,
  thinking,
  onSend,
  sound,
  onSound,
  latency,
  model,
  notify,
  seed,
  onSeedUsed,
  className = "",
}) {
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (seed) {
      setInput(seed);
      onSeedUsed?.();
      inputRef.current?.focus();
    }
  }, [seed, onSeedUsed]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const submit = (event) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || thinking) return;
    setInput("");
    onSend(text);
  };

  const handleKey = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const toggleMic = () => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      notify?.("Este navegador no tiene reconocimiento de voz. Probá con Chrome o Edge.", "error");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "es-AR";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join(" ");
      setInput(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  };

  return (
    <Panel
      title="Canal de voz"
      code="COM-03"
      icon={Radio}
      className={`chat-panel ${className}`}
      bodyClassName="chat__body"
      actions={
        <div className="chat__head-actions">
          <span className="panel__meta">{model || "walle"} · {latency ? `${latency}s` : "listo"}</span>
          <button type="button" className="icon-button icon-button--small" onClick={onSound} title={sound ? "Silenciar" : "Activar voz"}>
            {sound ? <Volume2 size={14} /> : <VolumeX size={14} />}
          </button>
        </div>
      }
    >
      <div className="chat-terminal-bar">
        <Terminal size={12} />
        <span>WALL-E://LOCAL</span>
        <i />
        <span>OLLAMA 11434</span>
        <i />
        <span>ES-AR</span>
      </div>

      <div className="chat-messages" ref={scrollRef} role="log" aria-live="polite">
        {messages.map((message) => (
          <motion.article
            key={message.id}
            className={`chat-message chat-message--${message.role} ${message.error ? "is-error" : ""}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22 }}
          >
            <div className="chat-message__meta">
              <span>{message.role === "user" ? "VOS" : message.role === "assistant" ? "WALL·E" : "SYS"}</span>
              <time>{message.time || shortClock()}</time>
              {message.seconds ? <em>{message.seconds}s</em> : null}
            </div>
            <div className="chat-message__bubble">
              {message.role === "system" ? <Sparkles size={12} /> : null}
              <p>{message.text}</p>
            </div>
          </motion.article>
        ))}

        <AnimatePresence>
          {thinking ? (
            <motion.div
              className="chat-message chat-message--assistant"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <div className="chat-message__meta"><span>WALL·E</span><time>PENSANDO</time></div>
              <div className="chat-message__bubble typing">
                <span /><span /><span />
                <em>procesando en local</em>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>

      <div className="chat-quick">
        {QUICK.map((text) => (
          <button
            key={text}
            type="button"
            className="quick-chip"
            onClick={() => {
              setInput("");
              onSend(text);
            }}
            disabled={thinking}
          >
            {text}
          </button>
        ))}
      </div>

      <form className="chat-composer" onSubmit={submit}>
        <div className="chat-composer__box">
          <span className="prompt-caret">&gt;</span>
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            maxLength={600}
            placeholder="Escribile a WALL·E…"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKey}
            aria-label="Mensaje para WALL-E"
          />
          <button
            type="button"
            className={`icon-button icon-button--small ${listening ? "is-recording" : ""}`}
            onClick={toggleMic}
            title={listening ? "Detener dictado" : "Dictar mensaje"}
          >
            {listening ? <MicOff size={15} /> : <Mic size={15} />}
          </button>
          <button
            type="submit"
            className="send-button"
            disabled={!input.trim() || thinking}
            aria-label="Enviar mensaje"
          >
            <Send size={16} />
          </button>
        </div>
        <div className="chat-composer__meta">
          <span><CornerDownLeft size={10} /> ENTER ENVÍA · SHIFT+ENTER SALTO</span>
          <span className={sound ? "is-on" : ""}>{sound ? "VOZ ON" : "VOZ OFF"}</span>
        </div>
      </form>
    </Panel>
  );
}
