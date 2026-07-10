# SongSeeker (Local Audio Edition) - AI Agent Guide

## Project Overview
SongSeeker is a self-hosted, offline-first music player designed for board games like Hitster. It uses QR code cards to play local MP3 files, eliminating "link rot" from YouTube or streaming links.

This is a heavily customized fork of the original SongSeeker project, focused exclusively on local audio playback (YouTube/Hitster/Rockster legacy code has been removed).

**Core value**: Scan a printed QR code → play the correct local MP3 from a random position with volume normalization.

## Key Architecture
- **Frontend** (`index.html`, `app.js`, `style.css`): Vanilla JavaScript (ES modules). Uses:
  - `qr-scanner` (from unpkg) for QR scanning.
  - `jsmediatags` for client-side ID3 metadata.
  - Web Audio API for dynamic range compression (volume normalization).
  - Local `<audio>` playback (preferred) + legacy YouTube paths removed.
- **Backend** (`backend/server.js`): Minimal Node.js HTTP server for report logging (broken links, wrong songs, etc.). Writes to `backend/reports.log`. No database.
- **Docker**:
  - Frontend served by Nginx (see `imagebuild/Dockerfile` + `imagebuild/default.conf`).
  - Separate backend container (`node:22-alpine`).
  - Music directory mounted as a volume (read-only recommended).
  - No pre-built images are published. Users must build from source or use git build context.
- **Workflow Tools** (Python, in `tools/`):
  - `workflow.py`: Interactive wizard for the full pipeline.
  - `deemix_download.py`: Download tracks from Deezer using ARL cookie.
  - `verify_music.py`: Fuzzy + exact matching, ID3 reading, optional AI verification (OpenAI-compatible), renaming.
  - `generate_cards.py`: Generate double-sided printable PDF QR cards (ReportLab + qrcode).
- **Tests**: Basic pytest in `tests/` (mainly for verify_music helpers).
- **Linting**: ESLint (JS) + Ruff/Black (Python). Run with `npm run check`.

## Running the Application

### Minimal Server (Recommended for most users - no tools)
No need to clone the full repo. Create this `docker-compose.yml` in a new directory:

```yaml
services:
  songseeker:
    build:
      context: https://github.com/uniplayer1/songseeker.git
      dockerfile: imagebuild/Dockerfile
    container_name: songseeker
    ports:
      - "8887:80"
    volumes:
      - ./music:/usr/share/nginx/html/music:ro
    restart: unless-stopped
```

```bash
mkdir -p music
docker compose up -d --build
```

Access at `http://localhost:8887`.

**Important**: Python tools (card generation, downloads, verification) are **not** available. Use full clone below if needed.

### Full Setup (with tools for adding songs/cards)
```bash
git clone https://github.com/uniplayer1/songseeker.git
cd songseeker
mkdir -p music/80s-90s music/rap music/schlager
# Copy your MP3s...
docker compose up -d --build
```

The project's `docker-compose.yml` includes both frontend and backend.

### Plain Docker
```bash
docker build -t songseeker -f imagebuild/Dockerfile .
docker run -d \
  --name songseeker \
  --restart unless-stopped \
  -p 8887:80 \
  -v "$(pwd)/music:/usr/share/nginx/html/music:ro" \
  songseeker
```

**Note**: Backend is recommended for full features (reports). Use the compose setup for that.

### Access
- Web UI: `http://localhost:8887` (or server IP).
- Reports work via the backend service.

**Music requirement**: Files should ideally follow `YYYY_Artist_Title.mp3` naming. The `verify_music.py` tool helps with this.

## Adding New Songs (Requires Full Clone + Tools)
1. `pip install -r tools/requirements.txt`
2. `cp .env.example .env` (fill `DEEMIX_ARL` for downloads, OpenAI key for AI verification)
3. `python tools/workflow.py` (recommended) or manual steps:
   - `deemix_download.py`
   - `verify_music.py` (supports `--verify-ai`, `--rename`)
   - `generate_cards.py`

See README for full details on CSV format, ARL tokens, etc.

## Configuration
- `.env` (loaded by Python tools via python-dotenv).
- Key vars: `DEEMIX_ARL`, `OPENAI_API_KEY`, `AI_MODEL` (see .env.example for current recommendations), `DEFAULT_BASE_URL`.
- Docker volumes handle music at runtime.

## Development
- **Lint & Test**: `npm run check` (or `npm run lint`, `npm run test:python`, etc.)
- **Python dev deps**: `pip install -r requirements-dev.txt` (ruff, black, pytest).
- **JS**: ESLint (flat config in `eslint.config.js`).
- **Docker**: `docker compose build` / `docker compose up -d --build`.
- Tests are lightweight (focus on core helpers like fuzzy matching and filename generation).

### Important Conventions
- Music filenames: `YYYY_Artist_Title.mp3` (umlauts preserved, special chars stripped).
- Cards use local URLs (e.g., `http://your-ip:8887/music/80s-90s/...`).
- Backend is for reports only (`/api/report`, `/api/reports`).
- No published Docker images on registries — always build from source or git context.
- The project is a **fork** and has diverged significantly (legacy YouTube code removed).

## CI / Workflow
- `.github/workflows/generate-docker-image.yml`: Builds the Docker image (multi-arch) on relevant changes only.
- Uses path filters so it skips unrelated commits (e.g., pure Python changes).
- Does **not** push to any registry.

## Gotchas & Notes
- **No Docker Hub / GHCR images**: Users must build. The minimal compose uses git context to avoid full local clone for runtime.
- **Tools require full source**: The minimal Docker run does not include `tools/`.
- **Deezer downloads**: Requires fresh ARL cookie (expires periodically).
- **AI verification**: Works with any OpenAI-compatible endpoint (Ollama, LM Studio, etc.). Batch size matters for cost/speed.
- **Reports**: Stored in flat `backend/reports.log`. The backend container must be running.
- **Music permissions**: Docker needs read access (`chmod -R 755 ./music` often needed).
- **Fork nature**: This repo has diverged from upstream. Do not assume upstream behavior.

## Key Files
- `docker-compose.yml` — Main orchestration (frontend + backend).
- `imagebuild/Dockerfile` + `imagebuild/default.conf` — Nginx image for frontend.
- `tools/workflow.py` — Main entry point for adding content.
- `app.js` — Core frontend logic (QR scanning, local playback, reports).
- `backend/server.js` — Report API.
- `tests/` — Python tests.
- `.env.example` — Configuration template.

## License
AGPL v3.

When working on this project as an agent:
- Prefer the minimal Docker path for runtime testing unless tools are needed.
- Run `npm run check` before suggesting code changes.
- Always consider that users may run the server-only version.
- Be aware of the .env requirements for any tool-related work.
- Do not assume images are pre-built on any registry.