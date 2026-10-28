const BASE = "";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* respuesta sin cuerpo */
  }
  if (!response.ok) {
    throw new Error(data?.error || `El servidor respondió ${response.status}`);
  }
  if (data && data.ok === false) {
    throw new Error(data.error || data.detail || "La operación no se pudo completar");
  }
  return data;
}

const post = (path, payload) =>
  request(path, { method: "POST", body: JSON.stringify(payload ?? {}) });

export const api = {
  state: () => request("/api/state"),
  events: (limit = 40) => request(`/api/events?limit=${limit}`),
  health: () => request("/api/health"),
  ports: () => request("/api/ports"),

  chat: (message) => post("/api/chat", { message }),

  move: (left, right, seconds) => post("/api/robot/move", { left, right, seconds }),
  drive: (left, right) => post("/api/robot/drive", { left, right }),
  stop: () => post("/api/robot/stop"),
  connect: (port) => post("/api/robot/connect", { port }),
  disconnect: () => post("/api/robot/disconnect"),
  emotion: (action) => post("/api/emotion", { action }),

  camera: (color) => request(`/api/camera/frame?color=${encodeURIComponent(color)}`),
  track: (enabled, color) => post("/api/vision/track", { enabled, color }),

  memory: {
    list: (query = "") => request(`/api/memory?q=${encodeURIComponent(query)}`),
    add: (text) => post("/api/memory", { text }),
    remove: (id) => request(`/api/memory/${id}`, { method: "DELETE" }),
  },

  agenda: {
    list: () => request("/api/agenda"),
    add: (payload) => post("/api/agenda", payload),
    remove: (index) => request(`/api/agenda?index=${index}`, { method: "DELETE" }),
  },

  settings: {
    get: () => request("/api/settings"),
    save: (payload) => post("/api/settings", payload),
  },

  diagnostics: () => request("/api/diagnostics"),
};
