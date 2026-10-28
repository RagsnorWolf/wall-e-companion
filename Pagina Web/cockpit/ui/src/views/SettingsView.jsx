import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  FileText,
  HardDrive,
  Loader2,
  RefreshCw,
  Save,
  Settings2,
  Wrench,
} from "lucide-react";
import { Panel } from "../components/ui/Panel";
import { ConnectionPanel } from "../components/panels/ConnectionPanel";
import { api } from "../lib/api";

export function SettingsView({
  state,
  ports,
  busy,
  onConnect,
  onDisconnect,
  onRefreshPorts,
  notify,
  refresh,
}) {
  const [settings, setSettings] = useState(null);
  const [models, setModels] = useState([]);
  const [paths, setPaths] = useState({});
  const [prompt, setPrompt] = useState("");
  const [checks, setChecks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ model: "walle", camera_index: 0, port: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [settingsData, diagnostics] = await Promise.all([
        api.settings.get(),
        api.diagnostics(),
      ]);
      setSettings(settingsData.settings || null);
      setModels(settingsData.models || []);
      setPaths(settingsData.paths || {});
      setPrompt(settingsData.prompt || "");
      setChecks(diagnostics.checks || []);
      setForm({
        model: settingsData.settings?.model || "walle",
        camera_index: settingsData.settings?.camera_index ?? 0,
        port: settingsData.settings?.port || "",
      });
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const save = useCallback(
    async (event) => {
      event.preventDefault();
      if (saving) return;
      setSaving(true);
      try {
        const data = await api.settings.save({
          model: form.model,
          camera_index: Number(form.camera_index),
          port: form.port || null,
        });
        notify(
          data.rebuild
            ? "Ajustes guardados. El cerebro se está reconstruyendo."
            : "Ajustes guardados.",
          "success"
        );
        setSettings(data.settings || null);
        refresh();
        load();
      } catch (error) {
        notify(error.message, "error");
      } finally {
        setSaving(false);
      }
    },
    [form, load, notify, refresh, saving]
  );

  const okCount = checks.filter((check) => check.ok).length;

  return (
    <div className="view-grid view-grid--settings">
      <Panel
        title="Núcleo y cámara"
        code="CFG-05"
        icon={Settings2}
        bodyClassName="settings__body"
        actions={
          <button
            type="button"
            className="icon-button icon-button--small"
            onClick={load}
            title="Recargar ajustes"
          >
            <RefreshCw size={13} />
          </button>
        }
      >
        {loading ? (
          <p className="empty-state">
            <Loader2 size={16} className="spin" /> Leyendo configuración…
          </p>
        ) : (
          <form className="settings-form" onSubmit={save}>
            <label className="field">
              <span>MODELO DE OLLAMA</span>
              <select
                value={form.model}
                onChange={(event) =>
                  setForm((current) => ({ ...current, model: event.target.value }))
                }
              >
                {(models.length ? models : [form.model]).map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
              <em>Cambiar el modelo reconstruye el cerebro y reinicia el enlace.</em>
            </label>

            <div className="field-row">
              <label className="field">
                <span>ÍNDICE DE CÁMARA</span>
                <input
                  type="number"
                  min="0"
                  max="12"
                  value={form.camera_index}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      camera_index: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="field">
                <span>PUERTO SERIAL</span>
                <input
                  value={form.port}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, port: event.target.value }))
                  }
                  placeholder="COM3 (opcional)"
                />
              </label>
            </div>

            <div className="settings-paths">
              <div>
                <HardDrive size={13} />
                <span>CEREBRO</span>
                <code>{paths.ai || "—"}</code>
              </div>
              <div>
                <Cpu size={13} />
                <span>MEMORIA</span>
                <code>{paths.memory || "—"}</code>
              </div>
              <div>
                <FileText size={13} />
                <span>AGENDA</span>
                <code>{paths.agenda || "—"}</code>
              </div>
            </div>

            <button
              type="submit"
              className="primary-button primary-button--wide"
              disabled={saving}
            >
              {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
              GUARDAR AJUSTES
            </button>
            <p className="mono-note">
              {settings
                ? `ACTIVO: ${settings.model} · CÁMARA ${settings.camera_index} · ${
                    settings.port || "SIN PUERTO"
                  }`
                : "SIN CONFIGURACIÓN CARGADA"}
            </p>
          </form>
        )}
      </Panel>

      <Panel
        title="Diagnóstico"
        code="DIA-05B"
        icon={Wrench}
        bodyClassName="diagnostics__body"
        actions={
          <span className="panel__meta">
            {okCount}/{checks.length} OK
          </span>
        }
      >
        <ul className="check-list">
          {checks.map((check) => (
            <li className={check.ok ? "is-ok" : "is-bad"} key={check.name}>
              {check.ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
              <div>
                <strong>{check.name}</strong>
                <span>{check.detail}</span>
              </div>
            </li>
          ))}
          {!checks.length ? (
            <li className="is-bad">
              <AlertTriangle size={15} />
              <div>
                <strong>Sin diagnóstico</strong>
                <span>El servidor no devolvió comprobaciones.</span>
              </div>
            </li>
          ) : null}
        </ul>
        <p className="mono-note">
          {state?.version ? `SERVIDOR v${state.version}` : "SERVIDOR LOCAL"} ·{" "}
          {state?.opencv ? "OPENCV OK" : "SIN OPENCV"} ·{" "}
          {state?.hardware ? "PYSERIAL OK" : "SIN PYSERIAL"}
        </p>
      </Panel>

      <ConnectionPanel
        state={state}
        ports={ports}
        onRefresh={onRefreshPorts}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
        busy={busy}
      />

      <Panel
        title="Personalidad"
        code="PRM-05C"
        icon={FileText}
        bodyClassName="prompt__body"
      >
        <p className="muted-copy">
          El prompt vive en <code>Modelo AI/prompts/system.md</code>. Para aplicar
          cambios, reconstruí el modelo con <code>build_model.py --create</code>.
        </p>
        <details className="prompt-details">
          <summary>Ver prompt del sistema</summary>
          <pre>{prompt || "No pude leer el prompt."}</pre>
        </details>
      </Panel>
    </div>
  );
}
