import { Activity, Bot, CalendarClock, Camera, Cpu, ShieldAlert, Sparkles } from "lucide-react";
import { Panel } from "../ui/Panel";
import { shortClock } from "../../lib/format";

const ICONS = {
  chat: Sparkles,
  robot: Bot,
  vision: Camera,
  memory: Cpu,
  agenda: CalendarClock,
  safety: ShieldAlert,
  serial: Activity,
  config: Cpu,
  tool: Cpu,
  emotion: Sparkles,
};

export function EventsPanel({ events, className = "", limit = 8, title = "Registro de actividad" }) {
  const visible = events.slice(0, limit);
  return (
    <Panel
      title={title}
      code="LOG-06"
      icon={Activity}
      className={`events-panel ${className}`}
      bodyClassName="events__body"
      actions={<span className="panel__meta">{events.length} EVENTOS</span>}
    >
      {visible.length ? (
        <ul className="event-list">
          {visible.map((event, index) => {
            const Icon = ICONS[event.kind] || Activity;
            return (
              <li className={`event event--${event.kind || "info"}`} key={`${event.ts}-${index}`}>
                <span className="event__icon"><Icon size={12} /></span>
                <div>
                  <p>{event.text}</p>
                  <time>{shortClock(new Date(event.ts * 1000))} · {(event.kind || "info").toUpperCase()}</time>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="empty-state">Todavía no hay actividad. Hablale a WALL·E o mové las orugas.</p>
      )}
    </Panel>
  );
}
