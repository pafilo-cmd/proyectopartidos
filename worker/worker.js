// Cloudflare Worker (plan gratuito): recibe el botón de la web y lanza el workflow de GitHub.
// El token de GitHub vive aquí como secreto, nunca en la web.
// Variables: REPO ("usuario/proyectopartidos"), ALLOWED_ORIGIN ("https://proyectopartidos.pureapps.es")
// Secreto:   GITHUB_TOKEN (token fine-grained solo para ese repo, permiso "Actions: read and write")

const WORKFLOW = "actualizar.yml";
const MIN_GAP_MS = 5 * 60 * 1000; // como mucho una búsqueda cada 5 minutos

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Content-Type": "application/json; charset=utf-8",
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST") return json({ ok: false, motivo: "Usa POST" }, 405, cors);
    if (request.headers.get("Origin") !== env.ALLOWED_ORIGIN) return json({ ok: false, motivo: "Origen no permitido" }, 403, cors);

    const gh = (path, init = {}) =>
      fetch(`https://api.github.com/repos/${env.REPO}${path}`, {
        ...init,
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "proyectopartidos-worker",
          "X-GitHub-Api-Version": "2022-11-28",
          ...(init.headers || {}),
        },
      });

    // ¿Hay ya una búsqueda en marcha o muy reciente?
    const runs = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
    if (runs.ok) {
      const last = (await runs.json()).workflow_runs?.[0];
      if (last) {
        const enMarcha = last.status === "queued" || last.status === "in_progress";
        const reciente = Date.now() - Date.parse(last.created_at) < MIN_GAP_MS;
        if (enMarcha || reciente) return json({ ok: true, estado: "en_marcha" }, 202, cors);
      }
    }

    const res = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: "main" }),
    });
    if (res.status === 204) return json({ ok: true, estado: "lanzada" }, 202, cors);
    return json({ ok: false, motivo: `GitHub respondió ${res.status}` }, 502, cors);
  },
};

function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), { status, headers });
}
