# 🎵 SongSeeker (Local Audio Edition)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Docker Support](https://img.shields.io/badge/Docker-Supported-blue?logo=docker)](https://www.docker.com/)
[![Made with JavaScript](https://img.shields.io/badge/Made%20with-JavaScript-F7DF1E?logo=javascript)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

A custom fork of [SongSeeker](https://github.com/andygruber/songseeker), optimized for **self-hosted, offline-capable music playback**. This version is specifically designed to eliminate "link rot" in board games like Hitster by hosting your own `.mp3` library.

This repository includes the game server **and** a complete workflow for creating printable QR-code cards from your local music collection — now with **automatic downloading from Deezer via deemix**.

> **Note:** Deezer no longer allows new developers to create apps, so playlist import via OAuth is no longer supported. The workflow now downloads tracks directly from your CSV using deemix.

---

## 📚 Table of Contents

- [Key Features](#key-features)
- [Quick Start (Game Server)](#quick-start-game-server)
- [Adding New Songs](#adding-new-songs)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Development & Quality](#development--quality)
- [License](#license)

---

## ✨ Key Features

*   **Offline First:** Host your own music library via Docker. No more broken YouTube links or region blocks.
*   **Automated Workflow:** Interactive wizard guides you from CSV → MP3 → Cards.
*   **Deezer Integration:** Automatically search and download tracks via deemix.
*   **AI-Powered Verification:** Optional OpenAI-compatible AI detects covers, instrumentals, live versions.
*   **Batch AI Processing:** Verify up to 30 songs per API call for speed and cost savings.
*   **Auto-Renaming:** Messy downloaded filenames become clean `YYYY_Artist_Title.mp3`.
*   **Umlaut-Safe:** Full support for German characters (ä, ö, ü, ß).
*   **Genre Folders:** Organize music into `music/80s/`, `music/Schlager/`, etc.
*   **Random Playback:** Custom "Game Mode" starts songs at random positions.
*   **Volume Normalization:** Built-in audio compressor for local files (ON by default).
*   **PWA Ready:** Install as a web app on your mobile device.

---

## 🚀 Quick Start (Game Server)

### Prerequisites
*   [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
*   Your music collection in `.mp3` or `.wav` format.

### Installation & Launch
```bash
git clone https://github.com/uniplayer1/songseeker.git
cd songseeker

# Create music folders
mkdir -p music/80s music/Schlager music/Movies

# Launch
docker compose up -d --build
```

Access the app at `http://<YOUR_SERVER_IP>:8887`.

> **Note:** Ensure Docker has read permissions: `chmod -R 755 ./music`

### Docker Usage Examples

#### Using Docker Compose (recommended)

The repository includes a `docker-compose.yml` that builds the image and starts both the web server and backend.

```bash
git clone https://github.com/uniplayer1/songseeker.git
cd songseeker

# Prepare your music directory (example)
mkdir -p music/80s-90s music/rap music/schlager
# Copy your .mp3 files into the appropriate subfolders

docker compose up -d --build
```

Access the app at `http://localhost:8887` (or your server's IP).

#### Using plain Docker

Build the image:

```bash
docker build -t songseeker -f imagebuild/Dockerfile .
```

Run the container (the backend is still recommended for full functionality like reports):

```bash
docker run -d \
  --name songseeker \
  -p 8887:80 \
  -v "$(pwd)/music:/usr/share/nginx/html/music:ro" \
  songseeker
```

**Note:** For the complete experience (including the backend for reports), use Docker Compose as shown above.

---

## 🎵 Adding New Songs
{#adding-new-songs}

### The Easy Way: Use the Wizard

Run the interactive wizard to handle everything:

```bash
# 1. Install dependencies (once)
pip install -r tools/requirements.txt

# 2. Set up your .env
cp .env.example .env
nano .env

# 3. Run the interactive wizard
python tools/workflow.py
```

The wizard guides you through:
1. Select CSV (with pre-check for issues)
2. Download with deemix (optional)
3. Verify, match & rename MP3s (AI optional)
4. Generate printable PDF cards

---

### Step by Step (Manual)

Prefer manual control? Here's the breakdown.

### Step 0: One-time Setup

```bash
pip install -r tools/requirements.txt
cp .env.example .env
nano .env
```

See [Configuration](#configuration) for details.

### Step 1: Create a Playlist CSV

Create a CSV for each genre. You only need `Artist`, `Title`, `Year` and optionally `backcol`.

**Example:** `playlists/80s.csv`

```csv
Artist,Title,Year,backcol
Mötley Crüe,Girls Girls Girls,1987,"1,0.5,0.5"
Bon Jovi,Livin' on a Prayer,1986,"0.5,1,0.5"
A-ha,Take On Me,1985,"0.75,0.2,0.75"
```

**Rules:**
- Use **commas** as delimiters with a **header row**.
- `backcol` is optional (card background color as `R,G,B` decimals 0–1).
- Wrap `backcol` in quotes: `"1,0.5,0.5"` so it doesn't split into columns.
- **Umlauts (ä, ö, ü, ß)** are fully supported.

**Tip:** Ask an LLM to generate a CSV:
> *"Create a CSV of 20 iconic 80s hits with columns Artist, Title, Year, backcol. Use RGB decimals 0–1 for backcol."*

### Step 2: Download with Deemix

Use `deemix_download.py` to fetch MP3s from a CSV (requires `DEEMIX_ARL` in `.env`).

```bash
python tools/deemix_download.py --from-csv playlists/80s.csv --output music/80s
```

See [Getting your ARL token](#getting-your-arl-token) and tool options for bitrate/delay. Messy filenames are cleaned in the next step.

### Step 3: Verify, Match & Rename

Use `verify_music.py` to match CSV entries to MP3s (exact + fuzzy), optionally with AI verification, rename to standard format, and export a local CSV.

```bash
# Recommended dry-run first
python tools/verify_music.py --csv playlists/80s.csv --music-dir music/80s --base-url http://.../music/80s

# With AI + rename
python tools/verify_music.py --csv playlists/80s.csv --music-dir music/80s --base-url http://... --verify-ai --rename --output-csv playlists/80s-local.csv
```

Key features: exact/fuzzy matching, AI checks (covers/instrumentals/etc.), auto-rename preserving umlauts, CSV export with local URLs.

See the tool's `--help` for full options.

### Step 4: Generate Cards

```bash
python tools/generate_cards.py playlists/80s-local.csv cards-80s.pdf
```

**Options:**
- `--flip short/long/none` (default `short`)
- `--icon ...` (embed icon in QR)
- `--color` (use backcol)
- `--set-name` (label set)

The PDF produces double-sided cards (QR on one side, info on the other). Test alignment with `--flip long|short|none`.

See tool `--help` for details. Print, cut, and play!

---

## ⚙️ Configuration

All settings live in a `.env` file (loaded automatically by the tools).

### Quick Setup
```bash
cp .env.example .env
nano .env
```

### Main Variables
| Variable          | Description |
|-------------------|-------------|
| `OPENAI_API_KEY`  | AI provider key |
| `OPENAI_API_BASE` | API endpoint (change for local providers) |
| `AI_MODEL`        | e.g. `gpt-5.6-luna`, `qwen3.6:7b` |
| `AI_BATCH_SIZE`   | Batch size for verification |
| `DEEMIX_ARL`      | Deezer cookie (see below) |
| `DEFAULT_BASE_URL`| Base URL for generated card links |
| `FUZZY_THRESHOLD` | Matching strictness |
| `ICON_PATH`       | Icon for QR codes |

### Provider Examples
See the `.env.example` file for full templates (OpenAI, Ollama, LM Studio, etc.).

### Deezer ARL Token
Required for downloading. Get it from your browser cookies after logging into deezer.com (see the "Getting your ARL token" section for details). A free account works.

---

## 🔑 Getting your ARL token

The `DEEMIX_ARL` is a cookie from your Deezer session (free account is fine). It is required for `deemix_download.py`.

**Recommended method (Browser):**
1. Log into [deezer.com](https://www.deezer.com).
2. Open DevTools (F12) → Application/Storage → Cookies → deezer.com.
3. Copy the value of the `arl` cookie (long string).
4. Add to `.env`: `DEEMIX_ARL=...`

**Easier alternatives:**
- Use the "Deezer ARL" browser extension.
- Or run the JS snippet in console while logged in: `document.cookie.split('; ').find(r => r.startsWith('arl=')).split('=')[1]`

**Notes:** ARLs can expire. For region issues, try a different account or VPN. See troubleshooting for download failures.

---

## 🤖 AI Verification Guide

### What it checks

When you use `--verify-ai`, the AI judges whether each file is:

| Check | Description |
|-------|-------------|
| `is_correct` | Does the file match the expected artist + title? |
| `is_cover` | Is it a cover version by another artist? |
| `is_instrumental` | Is it an instrumental / karaoke version? |
| `is_live` | Is it a live recording? |
| `is_remix` | Is it a remix or edit? |
| `suggested_filename` | AI suggests a clean filename if needed. |

### When to use it

- **Always** if you download from streaming services where metadata can be unreliable.
- **Recommended** when you have many fuzzy matches (messy filenames).
- **Optional** if you rip CDs yourself and trust the metadata.

### Cost estimate

With **gpt-5.6-luna** (or equivalent cheap model) and **batch size 20**:
- ~20 songs per API call
- ~$0.01–0.03 per call (prices vary; Luna is the most affordable tier)
- A 100-song playlist costs roughly **$0.05–0.15** (cheaper tiers like Luna or Terra reduce this significantly)

With **Ollama (local)**: Completely free, but slower.

### Tuning batch size

| Model | Recommended Batch | Notes |
|-------|-------------------|-------|
| gpt-5.6-luna | 20–30 | Fast, cheapest in the GPT-5.6 family |
| gpt-5.6-terra | 15–25 | Good balance of quality and cost |
| gpt-5.6-sol | 10–20 | Flagship model, highest accuracy |
| Qwen 3.6 27B | 8–15 | Excellent local all-rounder, strong reasoning/coding |
| Gemma 4 12B/27B | 5–12 | Google's latest, great for multimodal and efficiency |
| Llama 4 Scout | 5–10 | Meta's latest with very long context (up to 10M) |
| Mistral Medium 3.5 | 8–15 | Strong European open model, good instruction following |

If the AI returns garbage or truncates, **lower the batch size**.

---

## 🔤 File Naming & Umlauts

### Standard format

```
YYYY_Artist_Title.mp3
```

Examples:
```
1987_Mötley_Crüe_Girls_Girls_Girls.mp3
1986_Bon_Jovi_Livin'_on_a_Prayer.mp3
```

### Umlaut handling

- ✅ `ä`, `ö`, `ü`, `ß` — kept as-is
- ✅ `é`, `è`, `ç` — kept as-is
- ✅ `'` (apostrophe) — kept as-is
- ❌ `/`, `:`, `<`, `>`, `|`, `?`, `*`, `"` — removed
- ` ` (space) → `_` (underscore)

---

## 📁 Folder Structure (simplified)

```
songseeker/
├── .env
├── docker-compose.yml
├── index.html, app.js, style.css, manifest.json
├── icons/
├── music/               # your MP3s (mounted at runtime)
├── playlists/           # source CSVs (e.g. 80s.csv)
├── tools/               # Python scripts (wizard, verify, download, cards)
└── imagebuild/          # Dockerfile + nginx config
```

---

## 💡 Troubleshooting

### Matching issues
- "No match found": Lower `--fuzzy-threshold` (e.g. 0.3).
- Too many false matches: Raise threshold or use `--strict`.
- AI flags a good song: Try a stronger model (`gpt-5.6-terra`/`sol`) or lower batch size. Or skip `--verify-ai` if your source is trusted.

### Deemix / ARL problems
- Expired/invalid ARL: Get a fresh one (see [Getting your ARL token](#getting-your-arl-token)).
- Region-locked tracks: Try different account or tweak CSV artist/title (remove "feat.", version info).
- See tool output for specific errors.

### Card printing & scanning
- Alignment problems: Try `--flip long` or `--flip short`. Test on plain paper first.
- QR not scanning: Keep icon small (≤300px, transparent bg). Ensure `base-url` is reachable from the scanning device.

### Other
- Start time in cards: Append `?t=16` (or `?start=16`) to URLs in the generated CSV.
- See individual tool `--help` for more flags.

---

## 🏗️ Architecture

*   **Frontend:** Pure HTML5/CSS3/JavaScript (ES Modules).
*   **Scanning:** [qr-scanner](https://github.com/nimiq/qr-scanner).
*   **Metadata:** [jsmediatags](https://github.com/aadsm/jsmediatags).
*   **Backend:** Node.js for reports.
*   **Card Generator:** Python (ReportLab + qrcode).
*   **Workflow Tools:** Python (`requests`, `deemix`, `mutagen`, `rapidfuzz`, `openai`).

---

## 🛠️ Development & Quality

### Linting & Testing
```bash
pip install -r requirements-dev.txt
npm install
npm run check   # runs lint + tests
```

### Legacy Code
The frontend was slimmed for local audio only (YouTube/Hitster/Rockster paths removed). Old reports may still reference `YOUTUBE` type.

### Dependencies
See `requirements.txt` and `package.json` (dev). Deemix on PyPI is old; community forks may be needed for future work. Node backend updated to a recent LTS.

---

## ⚖️ License
Distributed under the GNU Affero General Public License v3.0. See `LICENSE` for more information.
