# SongSeeker (Local Audio Edition)

This is a custom fork of the [SongSeeker](https://github.com/andygruber/songseeker) project, modified to support **fully self-hosted, offline `.mp3` playback**. 

By hosting your own music files via a Docker container, you can completely avoid YouTube "link rot" (deleted videos, country restrictions, or changed URLs) ensuring your custom Hitster cards work forever.

## 🚀 Quick Setup Guide

### Prerequisites
* Docker and Docker Compose installed on your host machine / NAS.
* Your `.mp3` music files.

### 1. Clone the Repository
Clone this repository to your server:
```bash
git clone https://github.com/uniplayer1/songseeker.git
cd songseeker-local
```

### 2. Prepare Your Music Folder
Create a `music` directory in the root of the project and place your `.mp3` files inside it.
```bash
mkdir music
# Drop your .mp3 files into the ./music folder
```

**Crucial Step:** Ensure your host machine allows the Docker container to read these files by setting the correct permissions:
```bash
chmod -R 755 ./music
```

### 3. Build and Start the Container
Run the following command to build the custom Docker image and start up the web server:
```bash
docker compose up -d --build
```

### 4. Play!
* The SongSeeker app is now available at `http://<YOUR_SERVER_IP>:8887`.
* Your music files are accessible at `http://<YOUR_SERVER_IP>:8887/music/your-song.mp3`.
* When generating your custom Hitster QR codes, simply use your local network URL instead of a YouTube link!

---
**Troubleshooting:**
If you scan a QR code and get a "403 Forbidden" error, it means the web server doesn't have permission to read your music file. Run `chmod -R 755 ./music` again to fix it.