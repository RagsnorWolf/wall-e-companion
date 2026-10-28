import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BrainCircuit,
  Loader2,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Panel } from "../components/ui/Panel";
import { api } from "../lib/api";
import { shortClock } from "../lib/format";

function formatDate(ts) {
  if (!ts) return "—";
  const value = Number(ts);
  const date = new Date(value < 1e12 ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${shortClock(date)} · ${date.toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  })}`;
}

export function MemoryView({ state, notify, refresh }) {
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);
  const [query, setQuery] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const data = await api.memory.list(query);
        if (!alive) return;
        setItems(data.items || []);
        setCount(data.count || 0);
      } catch (error) {
        if (alive) notify(error.message, "error");
      } finally {
        if (alive) setLoading(false);
      }
    }, 220);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [query, tick, notify]);

  const add = useCallback(
    async (event) => {
      event.preventDefault();
      const clean = text.trim();
      if (!clean || saving) return;
      setSaving(true);
      try {
        await api.memory.add(clean);
        setText("");
        setTick((value) => value + 1);
        notify("Recuerdo guardado en la base local.", "success");
        refresh();
      } catch (error) {
        notify(error.message, "error");
      } finally {
        setSaving(false);
      }
    },
    [notify, refresh, saving, text]
  );

  const remove = useCallback(
    async (item) => {
      try {
        await api.memory.remove(item.id);
        setTick((value) => value + 1);
        notify("Recuerdo borrado.", "success");
        refresh();
      } catch (error) {
        notify(error.message, "error");
      }
    },
    [notify, refresh]
  );

  const facts = useMemo(
    () => items.filter((item) => item.kind !== "turn"),
    [items]
  );
  const turns = useMemo(() => items.filter((item) => item.kind === "turn"), [items]);

  return (
    <div className="view-grid view-grid--memory">
      <Panel
        title="Memoria persistente"
        code="MEM-03"
        icon={BrainCircuit}
        className="memory-panel"
        bodyClassName="memory__body"
        actions={<span className="panel__meta">{count} RECUERDOS</span>}
      >
        <form className="memory-add" onSubmit={add}>
          <div className="memory-add__box">
            <Sparkles size={16} />
            <input
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Algo que WALL·E tenga que recordar para siempre…"
              maxLength={500}
              aria-label="Nuevo recuerdo"
            />
            <button
              type="submit"
              className="primary-button"
              disabled={!text.trim() || saving}
            >
              {saving ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
              GUARDAR
            </button>
          </div>
          <p>
            Se guarda en <code>Modelo AI/memory.db</code>. Nada sale de tu
            computadora.
          </p>
        </form>

        <div className="memory-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar en los recuerdos…"
            aria-label="Buscar recuerdos"
          />
          {loading ? <Loader2 size={14} className="spin" /> : null}
        </div>

        <div className="memory-list">
          <AnimatePresence initial={false}>
            {items.map((item) => (
              <motion.article
                key={`${item.kind}-${item.id}-${item.ts}`}
                className={`memory-card ${item.kind === "turn" ? "is-turn" : ""}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: 12 }}
                transition={{ duration: 0.18 }}
              >
                <div className="memory-card__meta">
                  <span>{item.kind === "turn" ? "CONVERSACIÓN" : "DATO"}</span>
                  <time>{formatDate(item.ts)}</time>
                  <em>#{item.id}</em>
                </div>
                <p>{item.text}</p>
                <button
                  type="button"
                  className="icon-button icon-button--small"
                  onClick={() => remove(item)}
                  title="Borrar recuerdo"
                >
                  <Trash2 size={13} />
                </button>
              </motion.article>
            ))}
          </AnimatePresence>

          {!loading && !items.length ? (
            <p className="empty-state">
              {query
                ? `No encontré nada con “${query}”.`
                : "Todavía no hay recuerdos. Decile algo que quieras que no olvide."}
            </p>
          ) : null}
        </div>
      </Panel>

      <div className="memory-side">
        <Panel title="Resumen" code="MEM-03B" icon={BrainCircuit} bodyClassName="memory-summary">
          <div className="memory-stat">
            <strong>{count}</strong>
            <span>recuerdos totales</span>
          </div>
          <div className="memory-stat">
            <strong>{facts.length}</strong>
            <span>datos guardados</span>
          </div>
          <div className="memory-stat">
            <strong>{turns.length}</strong>
            <span>turnos de charla</span>
          </div>
          <p className="mono-note">
            {state?.memory != null
              ? `${state.memory} registros reportados por el cerebro`
              : "El cerebro todavía no reporta la base"}
          </p>
        </Panel>

        <Panel
          title="Cómo funciona"
          code="MEM-03C"
          icon={Sparkles}
          bodyClassName="howto__body"
        >
          <ul className="howto-list">
            <li>
              <Sparkles size={13} />
              <div>
                <strong>Contexto</strong>
                <p>Antes de responder, WALL·E busca recuerdos relevantes a tu mensaje.</p>
              </div>
            </li>
            <li>
              <BrainCircuit size={13} />
              <div>
                <strong>SQLite local</strong>
                <p>Los datos viven en tu disco. No hay nube ni cuenta.</p>
              </div>
            </li>
            <li>
              <Trash2 size={13} />
              <div>
                <strong>Control</strong>
                <p>Podés borrar cualquier recuerdo desde esta pantalla.</p>
              </div>
            </li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
