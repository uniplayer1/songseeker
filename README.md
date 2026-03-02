# 🎵 SongSeeker (Local Audio Edition)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Docker Support](https://img.shields.io/badge/Docker-Supported-blue?logo=docker)](https://www.docker.com/)
[![Made with JavaScript](https://img.shields.io/badge/Made%20with-JavaScript-F7DF1E?logo=javascript)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

A custom fork of [SongSeeker](https://github.com/andygruber/songseeker), optimized for **self-hosted, offline-capable music playback**. This version is specifically designed to eliminate "link rot" in board games like Hitster by hosting your own `.mp3` library.

---

## ✨ Key Features

*   **Offline First:** Host your own music library via Docker. No more broken YouTube links or region blocks.
*   **Dual Player Engine:** Seamlessly handles both local `.mp3` files and standard YouTube/Rockster/Hitster URLs.
*   **Smart Metadata:** Automatically extracts ID3 tags (Title, Artist, Year) from your local files.
*   **Random Playback:** Custom "Game Mode" starts songs at random positions for a specified duration to keep the game challenging.
*   **Modern UI:** Sleek dark mode interface with an animated equalizer and quick-access toolbar.
*   **PWA Ready:** Install it as a web app on your mobile device for a native feel.
*   **Issue Reporting:** Built-in reporting system to track broken links or incorrect metadata.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
*   [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on your server or NAS.
*   Your music collection in `.mp3` or `.wav` format.

### 2. Installation
```bash
git clone https://github.com/uniplayer1/songseeker.git
cd songseeker
```

### 3. Prepare Your Music
Create a `music` folder and copy your files into it.
```bash
mkdir music
# Copy your .mp3 files into ./music/
```

> **Note:** Ensure Docker has read permissions for your music:
> `chmod -R 755 ./music`

### 4. Launch
```bash
docker compose up -d --build
```

Access the app at `http://<YOUR_SERVER_IP>:8887`.

---

## 🛠️ Usage Tips

### Custom QR Codes
When generating QR codes for your custom Hitster cards, simply use the direct URL to your hosted music:
`http://<YOUR_SERVER_IP>:8887/music/song-name.mp3`

### Autoplay & iOS
Most mobile browsers (especially iOS) block autoplay with sound. SongSeeker includes an **"Audio Unlock"** mechanism:
1.  Click **"Start Scan"**.
2.  The app will perform a silent playback unlock.
3.  Once the QR is scanned, the song will play automatically (if enabled in settings).

### Reporting Songs
If a song is incorrect or has bad quality, use the **Report** button. Admins can view these reports by clicking the 📝 icon in the toolbar.

---

## 🏗️ Architecture

*   **Frontend:** Pure HTML5/CSS3/JavaScript (ES Modules).
*   **Scanning:** [qr-scanner](https://github.com/nimiq/qr-scanner) for fast, lightweight decoding.
*   **Metadata:** [jsmediatags](https://github.com/aadsm/jsmediatags) for client-side ID3 parsing.
*   **Backend:** Node.js micro-service for logging reports.
*   **Proxy:** Nginx for serving static files and routing API requests.

---

## ⚖️ License
Distributed under the GNU Affero General Public License v3.0. See `LICENSE` for more information.
