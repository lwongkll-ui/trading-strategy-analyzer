# Stock Selection — Docker deployment

Runs the page builder in a container and serves it privately through a
**Cloudflare Tunnel**, mirroring the `US_trading_platform` stack (nginx behind a
per-app `cloudflared`, no host ports, access gated by Cloudflare Zero Trust).
This is the chosen deployment path — it replaces the host-side
`run_refresh.bat` + Windows Task Scheduler job and the `wrangler`/Pages route in
`SETUP.md`, and it covers Milestones **B** (publish) and **C** (access control)
via the tunnel instead.

## Services (`docker-compose.yml`)

| Service | Image | Role |
|---|---|---|
| `builder` | `stock-select:latest` (this repo's `Dockerfile`) | Regenerates `site/index.html` from live data on a **weekday 21:00-HKT** loop; persists the fundamentals cache in `./cache`. |
| `web` | `nginx:alpine` | Serves `./site` read-only. **No host ports** — only `cloudflared` reaches it over the internal network. |
| `cloudflared` | `cloudflare/cloudflared` | Outbound-only tunnel (profile `tunnel`). Exposes `web` at your hostname. |

The build context is the **repo root**, because the app reads its constituent
CSVs from `../stock_tool/resources`; both trees are copied into the image.

## First run (local, no tunnel yet)

```bat
cd stock_select
docker compose build
docker compose up -d            # starts builder + web (cloudflared is opt-in)
```

- `builder` regenerates `site/index.html` immediately, then every weekday 21:00
  HKT. The **first live run fetches ~440 profiles** and Yahoo throttles at ~110
  per window, so early runs are partial; unresolved names stay uncached and are
  retried the next day, so the cache **converges over several days** on its own.
- Inspect: `docker compose logs -f builder`. The served file is `./site/index.html`.
- `web` serves it internally on port 80 — no host port is published, by design.

> Verify the image without touching Yahoo:
> `docker compose run --rm builder python main.py --demo --out /app/site/index.html`

## Publish it (Milestones B + C)

1. **Cloudflare Zero Trust → Networks → Tunnels →** create a *Cloudflared*
   tunnel and copy its **token**.
2. Add a **Public Hostname** on that tunnel, e.g.
   `stockselect.lwongkll-trading.com → HTTP → web:80`.
3. **Zero Trust → Access → Applications →** add a self-hosted app for that
   hostname with an **email-OTP policy** allowing your address. *(Milestone C —
   the page is private the moment the hostname resolves, so add this first.)*
4. `cp docker/.env.example docker/.env`, paste the token into `TUNNEL_TOKEN`.
5. Start the tunnel:

```bat
docker compose --profile tunnel up -d
```

`docker/.env` is gitignored — never commit the token.

## Operating notes

- **Update after code changes:** `docker compose build && docker compose up -d`.
- **Force a rebuild now:** `docker compose restart builder` (runs once on start),
  or `docker compose run --rm builder python main.py --out /app/site/index.html`.
- **Local URL:** http://localhost:8088 (bound to 127.0.0.1 — this machine only,
  bypasses the Access login). Public access stays via the tunnel.
- **Stop:** `docker compose --profile tunnel down`.
- **Same outbound IP** as the host, so Yahoo's throttle behaviour is unchanged —
  do not lower the daily spacing or raise `PROFILE_WORKERS` to rush convergence.
- `cache/`, `reports/`, `site/` and `docker/.env` are gitignored.
