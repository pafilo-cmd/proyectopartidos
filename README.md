# proyectopartidos

Web de prueba que dice en qué canal y en qué dial de cada plataforma se emite un partido.
Se publica en **https://proyectopartidos.pureapps.es** con GitHub Pages. Todo con planes gratuitos.

## Cómo funciona

```
cada 3 h o botón de la web ──► GitHub Actions ──► scripts/update.py ──► docs/data.json ──► GitHub Pages
         ▲                                                 │
         └── Cloudflare Worker (guarda el token) ◄─────────┘   la web lee data.json
```

- `data/manual.json`: partidos metidos a mano. Cada fuente que se lista cuenta como un voto.
- `data/diales.json`: la tabla de diales por plataforma. Se mantiene a mano.
- `scripts/update.py`: junta las fuentes, coteja y escribe `docs/data.json`.
  - **confirmado**: dos o más fuentes dicen el mismo canal.
  - **probable**: solo hay una fuente.
  - **conflicto**: las fuentes dicen canales distintos.
- Fuentes automáticas: de momento solo **TheSportsDB**, con su clave gratuita, que devuelve pocos partidos. Las webs españolas y la EPG quedan para la siguiente fase.
- `docs/index.html`: la web. El botón **Buscar datos nuevos** pide una búsqueda al Worker y espera a que cambie `data.json` (tarda 2–3 min).

## Puesta en marcha (una sola vez)

### 1. Repo y GitHub Pages
1. Crea un repo **público** llamado `proyectopartidos` en GitHub. Pages y Actions son gratis en repos públicos, y sube este proyecto tal cual.
2. En el repo, ve a **Settings → Pages → Source** y elige **GitHub Actions**.
3. En **Actions**, abre "Actualizar partidos" y pulsa **Run workflow**. Al terminar, la web queda publicada en `https://pafilo-cmd.github.io/proyectopartidos/`.

### 2. Subdominio proyectopartidos.pureapps.es
1. En el DNS de pureapps.es (donde tengas el dominio) añade este registro:
   `CNAME  proyectopartidos  →  pafilo-cmd.github.io`
2. En **Settings → Pages → Custom domain** escribe `proyectopartidos.pureapps.es`, guarda y, cuando lo permita, marca **Enforce HTTPS**.
   El DNS puede tardar desde unos minutos hasta unas horas en propagarse.

### 3. Botón "Buscar datos nuevos" (Cloudflare Worker, gratis)
1. Crea un token *fine-grained* en GitHub (**Settings → Developer settings → Fine-grained tokens**):
   - Repository access: solo `proyectopartidos`.
   - Permissions: **Actions: Read and write**. No hace falta ningún permiso más.
2. Despliega el Worker:
   ```bash
   cd worker
   # edita wrangler.toml: REPO = "pafilo-cmd/proyectopartidos"
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN     # pega el token
   npx wrangler deploy                      # te da una URL *.workers.dev
   ```
3. Pega esa URL en `docs/index.html`, en `const WORKER_URL = '...'`, y haz commit.

Mientras `WORKER_URL` esté vacío, el botón solo recarga los datos que ya hay.
El Worker solo acepta peticiones desde `https://proyectopartidos.pureapps.es` y como mucho lanza una búsqueda cada 5 minutos.

## Mantenimiento
- **Diales**: edita `data/diales.json`. Los de Movistar satélite están casi todos vacíos y hay que rellenarlos a mano.
- **Partidos a mano**: añádelos en `data/manual.json` con su canal y sus fuentes.
- Si el script ve un canal que no está en `diales.json`, lo apunta en `avisos` dentro de `data.json` y en el log del workflow.
- El cron hace commit de `data.json` en cada pasada, así que GitHub no lo desactiva por inactividad.

## Probar en local
```bash
python3 scripts/update.py
cd docs && python3 -m http.server 8000   # abre http://localhost:8000
```
