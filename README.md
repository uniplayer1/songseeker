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
- [Adding New Songs — The Easy Way](#adding-new-songs--the-easy-way)
- [Adding New Songs — Step by Step](#adding-new-songs--step-by-step)
  - [Step 0: One-time Setup](#step-0-one-time-setup)
  - [Step 1: Create a Playlist CSV](#step-1-create-a-playlist-csv)
  - [Step 2: Download with Deemix](#step-2-download-with-deemix)
  - [Step 3: Verify, Match & Rename](#step-3-verify-match--rename)
  - [Step 4: Generate Cards](#step-4-generate-cards)
- [Configuration (.env)](#configuration-env)
- [Getting your ARL token](#getting-your-arl-token)
- [AI Verification Guide](#ai-verification-guide)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
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

---

## 🎵 Adding New Songs — The Easy Way

### Just run the wizard:

```bash
# 1. Install dependencies (once)
pip install -r tools/requirements.txt

# 2. Set up your .env
cp .env.example .env
nano .env

# 3. Run the interactive wizard
python tools/workflow.py
```

The wizard will guide you through every step:
1. ✅ Select your CSV playlist (with automatic pre-check)
2. ✅ Download with deemix (optional)
3. ✅ Verify, match & rename MP3s (with optional AI verification)
4. ✅ Generate printable PDF cards (choose icon & color options)

---

## 🎵 Adding New Songs — Step by Step

If you prefer running each step manually, here is the full breakdown.

### Step 0: One-time Setup

```bash
# Install Python dependencies
pip install -r tools/requirements.txt

# Create your configuration file
cp .env.example .env
nano .env
```

Fill in at least the tokens you need. See [Configuration (.env)](#configuration-env) for details.

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

**Tip:** Ask ChatGPT/Claude to generate a CSV:
> *"Create a CSV of 20 iconic 80s hits with columns Artist, Title, Year, backcol. Use RGB decimals 0–1 for backcol."*

**Pre-check:** When you run the wizard, it automatically checks your CSV for empty rows, duplicates, and missing years and asks if you want to continue or fix them first.

### Step 2: Download with Deemix

Download the tracks as MP3s using deemix directly from your CSV playlist.

```bash
python tools/deemix_download.py \
  --from-csv playlists/80s.csv \
  --output music/80s
```

This searches Deezer for each track in the CSV and downloads it individually.

**Prerequisites:**
You need a valid `DEEMIX_ARL` token in your `.env` file. See [Getting your ARL token](#getting-your-arl-token) below.

**Options:**
- `--bitrate 320` (default) or `--bitrate flac` or `--bitrate 128`
- `--delay 0.2` — delay between API searches (Deezer rate limit: ~50 req / 5 sec)

After downloading, your folder will look like:

```
music/80s/
├── 01 - Mötley Crüe - Girls Girls Girls.mp3
├── 02 - Bon Jovi - Livin' On A Prayer.mp3
└── ...
```

> Don't worry about messy filenames! The next step cleans them up.

### Step 3: Verify, Match & Rename

The `verify_music.py` tool scans your music folder, matches each CSV entry to an MP3, and renames files to the standard format.

```bash
# Dry-run first (recommended)
python tools/verify_music.py \
  --csv playlists/80s.csv \
  --music-dir music/80s \
  --base-url http://192.168.1.100:8887/music/80s

# With AI verification
python tools/verify_music.py \
  --csv playlists/80s.csv \
  --music-dir music/80s \
  --base-url http://192.168.1.100:8887/music/80s \
  --verify-ai

# Rename and generate card CSV
python tools/verify_music.py \
  --csv playlists/80s.csv \
  --music-dir music/80s \
  --base-url http://192.168.1.100:8887/music/80s \
  --rename \
  --output-csv playlists/80s-local.csv
```

**What it does:**

| Feature | Description |
|---------|-------------|
| **Exact matching** | Finds files already named `YYYY_Artist_Title.mp3`. |
| **Fuzzy matching** | Matches messy filenames using metadata + filename similarity. |
| **AI verification** | Sends ID3 tags to AI to confirm it's the correct song (not a cover/instrumental). |
| **Issue flags** | Reports covers, instrumentals, live recordings, remixes, and missing files. |
| **Auto-rename** | Renames matched files to clean standard while preserving sub-folders and umlauts. |
| **CSV export** | Generates a card-ready CSV with local URLs pointing to your server. |

After renaming:

```
music/80s/
├── 1987_Mötley_Crüe_Girls_Girls_Girls.mp3
├── 1986_Bon_Jovi_Livin'_on_a_Prayer.mp3
└── ...
```

### Step 4: Generate Cards

```bash
python tools/generate_cards.py \
  playlists/80s-local.csv \
  cards-80s.pdf
```

**Options:**
- `--flip short/long/none` — Double-sided alignment (default: `short`, book-style)
- `--icon icons/icon-96x96.png` — Embed an icon in the QR codes
- `--color` — Use the `backcol` column from your CSV for colored card backs

**Double-sided printing:**
The PDF has QR codes on odd pages and text (Artist/Title/Year) on even pages. When printing double-sided, the cards must align perfectly so each card has QR on front and text on back.

Most printers default to **"flip on long edge"** (like a calendar). If your cards don't align, try:

```bash
# Flip on long edge (vertical mirror, top ↔ bottom)
python tools/generate_cards.py \
  playlists/80s-local.csv cards-80s.pdf --flip long

# Flip on short edge (horizontal mirror, left ↔ right, like a book)
python tools/generate_cards.py \
  playlists/80s-local.csv cards-80s.pdf --flip short

# No mirror (print single-sided or align manually)
python tools/generate_cards.py \
  playlists/80s-local.csv cards-80s.pdf --flip none
```

> **Tip:** Do a test print on plain paper first, hold it up to a light, and check if front/back align before printing on cardstock.

Print the PDF, cut the cards, and play!

---

## ⚙️ Configuration (.env)

All persistent settings go into a `.env` file in the project root. The tools load it automatically.

### Quick Setup

```bash
cp .env.example .env
nano .env
```

### Full Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(empty)* | AI API key. Get one at [OpenAI](https://platform.openai.com/api-keys). |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | API endpoint. Change for Ollama, LM Studio, etc. |
| `AI_MODEL` | `gpt-4o-mini` | Model name. Use `gpt-4o` for better quality. |
| `AI_BATCH_SIZE` | `20` | Songs verified per API call. Lower for local models. |
| `DEEMIX_ARL` | *(empty)* | Deezer ARL cookie for downloading with deemix. See [Getting your ARL token](#getting-your-arl-token) below. |
| `DEFAULT_BASE_URL` | *(empty)* | Your SongSeeker root URL (e.g. `http://nas:8887/music`). The genre subfolder is appended automatically (e.g. `.../music/80s`). |
| `FUZZY_THRESHOLD` | `0.45` | Match strictness (0.0–1.0). |
| `ICON_PATH` | `icons/icon-96x96.png` | QR code icon for cards. |

### Provider Examples

**OpenAI (default):**
```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_BASE=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_BATCH_SIZE=20
```

**Ollama (local, free, private):**
```env
OPENAI_API_KEY=ollama
OPENAI_API_BASE=http://localhost:11434/v1
AI_MODEL=llama3.1
AI_BATCH_SIZE=5
```

**LM Studio:**
```env
OPENAI_API_KEY=lm-studio
OPENAI_API_BASE=http://localhost:1234/v1
AI_MODEL=local-model
AI_BATCH_SIZE=5
```

---

## 🔑 Getting your ARL token

The ARL is a long cookie from your Deezer login session. It lets deemix search and download tracks. **A free Deezer account is sufficient.**

### Option 1 — Browser (recommended)

1. Open your browser and go to **https://www.deezer.com**
2. **Log in** to your Deezer account (create a free one if needed)
3. Open **Developer Tools**:
   - Chrome/Edge: `F12` or `Ctrl+Shift+I`
   - Firefox: `F12` or `Ctrl+Shift+K`
4. Go to the **Application** (Chrome) or **Storage** (Firefox) tab
5. In the left sidebar, click **Cookies → https://www.deezer.com**
6. Find the row with **Name = `arl`**
7. Double-click the **Value** field and copy the entire string (about 192 characters)
8. Open your `.env` file and add:
   ```env
   DEEMIX_ARL=your_copied_value
   ```

### Option 2 — Browser Extension (easiest)

Install the **"Deezer ARL"** browser extension (available for Chrome/Firefox). It shows your ARL with one click.

### Option 3 — JavaScript Console

1. Go to https://www.deezer.com and log in
2. Open Developer Tools → **Console**
3. Paste this and press Enter:
   ```javascript
   document.cookie.split('; ').find(r => r.startsWith('arl=')).split('=')[1]
   ```
4. Copy the printed string

### Troubleshooting ARL issues

- **ARL expires:** If downloads stop working, get a fresh ARL (repeat the steps above).
- **Region locks:** Some tracks may not be available in your country even with a valid ARL.
- **Account type:** A free Deezer account works fine for deemix.

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

With **GPT-4o-mini** and **batch size 20**:
- ~20 songs per API call
- ~$0.01–0.03 per call
- A 100-song playlist costs roughly **$0.05–0.15**

With **Ollama (local)**: Completely free, but slower.

### Tuning batch size

| Model | Recommended Batch | Notes |
|-------|-------------------|-------|
| GPT-4o-mini | 20–30 | Fast, cheap, large context |
| GPT-4o | 15–20 | Better accuracy |
| Llama 3.1 (8B) | 5–10 | Local, free, smaller context |
| Mistral (7B) | 5–10 | Local, free, smaller context |

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

## 📁 Folder Structure Example

```
songseeker/
├── .env                          ← your configuration
├── .env.example                  ← template
├── docker-compose.yml
├── index.html
├── app.js
├── style.css
├── icons/
│   └── icon-96x96.png
├── music/                        ← downloaded MP3s
│   ├── 80s/
│   │   ├── 1987_Mötley_Crüe_Girls_Girls_Girls.mp3
│   │   └── ...
│   ├── Schlager/
│   └── Movies/
├── playlists/                    ← source CSVs
│   ├── 80s.csv
│   └── Schlager.csv
├── playlists-local/              ← generated card-ready CSVs
│   ├── 80s-local.csv
│   └── Schlager-local.csv
├── cards/                        ← generated PDFs
│   ├── cards-80s.pdf
│   └── cards-Schlager.pdf
├── tools/
│   ├── requirements.txt
│   ├── workflow.py               ← interactive wizard ⭐
│   ├── verify_music.py           ← verify & rename
│   ├── deemix_download.py        ← download MP3s
│   └── generate_cards.py         ← PDF card generator
└── README.md                     ← this file
```

---

## 💡 Troubleshooting

### "No match found" for a song I know exists

Lower the fuzzy threshold:
```bash
python tools/verify_music.py ... --fuzzy-threshold 0.3
```

### AI says a correct song is "incorrect"

Check the `confidence` score. If it's low (< 0.7), the AI is uncertain. You can:
- Use a better model (`gpt-4o` instead of `gpt-4o-mini`)
- Lower the batch size
- Skip AI verification if you trust the source

### Too many false fuzzy matches

Raise the fuzzy threshold:
```bash
python tools/verify_music.py ... --fuzzy-threshold 0.6
```

Or use `--strict` for exact matches only.

### Deemix download fails / ARL invalid

- Make sure you're logged into Deezer in the browser where you copied the ARL.
- The ARL expires after a while. Get a fresh one from your browser cookies. See [Getting your ARL token](#getting-your-arl-token).
- Make sure your Deezer account can play the songs (some tracks are region-locked).
- If a specific song is not found, tweak the artist/title in your CSV:
  - Remove featured artists: `"Kylie Minogue and Jason Donovan"` → `"Kylie Minogue"`
  - Remove version info: `"(MTV Unplugged)"` → remove it
  - Then re-run `deemix_download.py`

### Cards don't align when printing double-sided

This depends on your printer's default duplex mode. Most printers flip on the **long edge** (like a calendar), but the card generator defaults to **short edge** (like a book page).

Fix it by passing the `--flip` option:
```bash
# Try this first (most common)
python tools/generate_cards.py ... --flip long

# If that doesn't work, try the other direction
python tools/generate_cards.py ... --flip short

# For single-sided printing or manual alignment
python tools/generate_cards.py ... --flip none
```

> **Tip:** Print one test page on plain paper, hold it up to a light, and check if front/back align before printing the full deck on cardstock.

### Cards don't scan properly

- The QR icon should be ≤ 300×300 px with a transparent background.
- Make sure your `base-url` is reachable from the device that scans the QR code.

### Adding start times to songs

Append `?t=16` to the URL in the generated CSV before running `generate_cards.py`:

```csv
Artist,Title,Year,URL,backcol
Bon Jovi,Livin' on a Prayer,1986,http://nas:8887/music/80s/1986_Bon_Jovi_Livin'_on_a_Prayer.mp3?t=16,"0.5,1,0.5"
```

---

## 🏗️ Architecture

*   **Frontend:** Pure HTML5/CSS3/JavaScript (ES Modules).
*   **Scanning:** [qr-scanner](https://github.com/nimiq/qr-scanner) for fast decoding.
*   **Metadata:** [jsmediatags](https://github.com/aadsm/jsmediatags) for client-side ID3 parsing.
*   **Backend:** Node.js micro-service for logging reports.
*   **Proxy:** Nginx for serving static files and routing API requests.
*   **Card Generator:** Python (ReportLab + qrcode).
*   **Workflow Tools:** Python utilities (`requests`, `deemix`, `mutagen`, `rapidfuzz`, `openai`).

---

## ⚖️ License
Distributed under the GNU Affero General Public License v3.0. See `LICENSE` for more information.
