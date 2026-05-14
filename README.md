# PLUM Downloader
<div align="center">
  
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blueviolet.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#download)
[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![GitHub Release](https://img.shields.io/github/v/release/ArtificialT800/CompanionApp?color=blueviolet)](https://github.com/ArtificialT800/CompanionApp/releases)

**Search and download music to your Android device.**

A local desktop app that runs entirely on your machine. No accounts, no cloud, nothing leaves your network.

[Download for Windows / macOS / Linux](https://github.com/ArtificialT800/CompanionApp/releases) &nbsp;·&nbsp;

</div>

## What is PLUM Downloader?

PLUM Downloader is a desktop app that runs a local web server on your PC. Open it in your browser, search for music, download it with full metadata and album art, then transfer it directly to your Android device over WiFi - no cables, no accounts, no third-party services involved.

Designed to pair with a local Android music player. [Get the Android app.](https://github.com/ArtificialT800/PLUMM)

---

## Features

**Search and Download**
- Search by song name or paste a YouTube URL directly
- Downloads in M4A or MP3 format
- Automatic metadata tagging - title, artist, album, year
- Album art embedded directly into the file
- Genre lookup via iTunes Search API with MusicBrainz fallback
**Playlist Import**
- Import Spotify playlists via an Exportify CSV export
- Import YouTube playlists by URL
- Per-track Deezer enrichment for metadata and artwork
- Pre-selects tracks you do not already have locally
- Export as a `.plumm` playlist file - import directly into the Android app
**WiFi Transfer**
- Transfer downloaded files directly to your Android device over WiFi
- No cables, no USB debugging, no cloud sync
- Drag and drop from the browser interface
**Private by design**
- Runs entirely on your local network
- No accounts, no telemetry, nothing uploaded anywhere
- Cookies for YouTube authentication stored locally and never leave your machine
---

## Download

Pre-built binaries for all platforms are attached to every [GitHub Release](https://github.com/ArtificialT800/CompanionApp/releases).

| Platform | File |
|----------|------|
| Windows | `PlumDownloader.exe` |
| macOS | `PlumDownloader-macos.zip` |
| Linux | `PlumDownloader-linux.tar.gz` |

---

## Usage

1. Download and run the file for your platform
2. A browser window opens automatically at `http://localhost:7823`
3. Search for music, or paste a YouTube URL or playlist link
4. Download your tracks - metadata and art are fetched automatically
5. Transfer to your Android device via the WiFi transfer tab
---

## License

PLUM Downloader is open source under the [GNU Affero General Public License v3.0](LICENSE).

---

## Building from Source

For developers who want to run or modify the app directly.

### Requirements

- Python 3.11+
- pip
- Deno (required for YouTube signature solving via yt-dlp-ejs)
### Setup

```bash
# Clone the repo
git clone https://github.com/ArtificialT800/CompanionApp.git
cd CompanionApp

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Then open `http://localhost:7823` in your browser.

### Building a standalone executable

```bash
pyinstaller PlumDownloader.spec
```

Output lands in `dist/`. The `.spec` file is included in the repo and handles all `--add-data` paths and hidden imports for all three platforms.

---

<div align="center">
Made by <a href="https://www.instagram.com/artificialt800/">Arti R</a>
</div>
