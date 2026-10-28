import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CalendarClock,
  CalendarPlus,
  Clock,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import { Panel } from "../components/ui/Panel";
import { api } from "../lib/api";

const DATE_TIME = new Intl.DateTimeFormat("es-AR", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatMoment(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return DATE_TIME.format(date).replace(/\./g, "").toUpperCase();
}

function localNow() {
  const now = new Date();
  now.setMinutes(now.getMinutes() + 30);
  const pad = (number) => String(number).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(
    now.getHours()
  )}:${pad(now.getMinutes())}`;
}

export function AgendaView({ notify }) {
  const [events, setEvents] = useState([]);
  const [google, setGoogle] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    titulo: "",
    inicio: localNow(),
    duracion_minutos: 60,
    descripcion: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.agenda.list();
      setEvents(data.events || []);
      setGoogle(Boolean(data.google));
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const add = useCallback(
    async (event) => {
      event.preventDefault();
      if (!form.titulo.trim() || !form.inicio || saving) return;
      setSaving(true);
      try {
        const data = await api.agenda.add({
          titulo: form.titulo.trim(),
          inicio: form.inicio,
          duracion_minutos: Number(form.duracion_minutos) || 60,
          descripcion: form.descripcion.trim(),
        });
        setEvents(data.events || []);
        setForm((current) => ({
          ...current,
          titulo: "",
          descripcion: "",
          inicio: localNow(),
        }));
        notify("Evento agendado.", "success");
      } catch (error) {
        notify(error.message, "error");
      } finally {
        setSaving(false);
      }
    },
    [form, notify, saving]
  );

  const remove = useCallback(
    async (index) => {
      try {
        const data = await api.agenda.remove(index);
        setEvents(data.events || []);
        notify("Evento borrado.", "success");
      } catch (error) {
        notify(error.message, "error");
      }
    },
    [notify]
  );

  const update = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  return (
    <div className="view-grid view-grid--agenda">
      <Panel
        title="Nuevo evento"
        code="AGD-04"
        icon={CalendarPlus}
        bodyClassName="agenda-form__body"
      >
        <form className="agenda-form" onSubmit={add}>
          <label className="field">
            <span>TÍTULO</span>
            <input
              value={form.titulo}
              onChange={update("titulo")}
              placeholder="Llamada con Agus, revisar servos…"
              maxLength={140}
              required
            />
          </label>

          <div className="field-row">
            <label className="field">
              <span>FECHA Y HORA</span>
              <input
                type="datetime-local"
                value={form.inicio}
                onChange={update("inicio")}
                required
              />
            </label>
            <label className="field">
              <span>DURACIÓN (MIN)</span>
              <input
                type="number"
                min="5"
                max="480"
                step="5"
                value={form.duracion_minutos}
                onChange={update("duracion_minutos")}
              />
            </label>
          </div>

          <label className="field">
            <span>DESCRIPCIÓN</span>
            <textarea
              rows={3}
              value={form.descripcion}
              onChange={update("descripcion")}
              placeholder="Detalles opcionales…"
              maxLength={500}
            />
          </label>

          <button
            type="submit"
            className="primary-button primary-button--wide"
            disabled={!form.titulo.trim() || saving}
          >
            {saving ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
            AGENDAR
          </button>
          <p className="mono-note">
            {google
              ? "GOOGLE CALENDAR CONFIGURADO"
              : "AGENDA LOCAL · GOOGLE CALENDAR NO CONFIGURADO"}
          </p>
        </form>
      </Panel>

      <Panel
        title="Agenda"
        code="AGD-04B"
        icon={CalendarClock}
        className="agenda-list-panel"
        bodyClassName="agenda-list__body"
        actions={<span className="panel__meta">{events.length} EVENTOS</span>}
      >
        {loading ? (
          <p className="empty-state">
            <Loader2 size={16} className="spin" /> Leyendo la agenda…
          </p>
        ) : null}

        <div className="agenda-list">
          <AnimatePresence initial={false}>
            {events.map((event, index) => (
              <motion.article
                key={`${event.inicio}-${event.titulo}-${index}`}
                className="agenda-card"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: 14 }}
                transition={{ duration: 0.18 }}
              >
                <div className="agenda-card__date">
                  <CalendarClock size={18} />
                  <span>{formatMoment(event.inicio)}</span>
                </div>
                <div className="agenda-card__copy">
                  <strong>{event.titulo}</strong>
                  {event.descripcion ? <p>{event.descripcion}</p> : null}
                  <span className="agenda-card__meta">
                    <Clock size={11} /> {formatMoment(event.inicio)} →{" "}
                    {formatMoment(event.fin)}
                  </span>
                </div>
                <button
                  type="button"
                  className="icon-button icon-button--small"
                  onClick={() => remove(index)}
                  title="Borrar evento"
                >
                  <Trash2 size={13} />
                </button>
              </motion.article>
            ))}
          </AnimatePresence>

          {!loading && !events.length ? (
            <p className="empty-state">
              No hay eventos todavía. Agendá el primero a la izquierda.
            </p>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}
