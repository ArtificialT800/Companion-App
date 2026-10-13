# PLUM Downloader
<div align="center">
  
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blueviolet.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#download)
[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![GitHub Release](https://img.shields.io/github/v/release/ArtificialT800/Companion-App?color=blueviolet)](https://github.com/ArtificialT800/Companion-App/releases)

**Search and download music to your Android device.**

A local desktop app that runs entirely on your machine. No accounts, no cloud, nothing leaves your network.

[Download for Windows / macOS / Linux](https://github.com/ArtificialT800/Companion-App/releases) &nbsp;

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
- Logs stay on your machine, and your personal folder paths and username are replaced automatically before anything is written to them
---

## Download

Pre-built binaries for all platforms are attached to every [GitHub Release](https://github.com/ArtificialT800/Companion-App/releases).

| Platform | File | How to run |
|----------|------|------------|
| Windows | `PlumDownloader-windows.zip` | Unzip, then run `PlumDownloader.exe` inside the folder. Keep the folder together. |
| macOS | `PlumDownloader-macos.zip` | Unzip, then open `PlumDownloader.app`. |
| Linux | `PlumDownloader-linux.tar.gz` | Extract with `tar -xzf PlumDownloader-linux.tar.gz`, then run `PlumDownloader` inside the folder. |

---

## Usage

1. Download the file for your platform, extract it and run it
2. A browser window opens automatically at `http://localhost:7823`
3. Search for music, or paste a YouTube URL or playlist link
4. Download your tracks - metadata and art are fetched automatically
5. Transfer to your Android device via the WiFi transfer tab

### Opening and closing

- Only one copy of the app runs at a time. Launching it again while it is open just opens a new browser tab on the running copy.
- Closing the browser tab quits the app within a few seconds. If you have several tabs open, it quits when the last one closes.
- If downloads are still running when you close the tab, the app waits for them to finish and then quits.
- If the browser crashes, the app quits on its own after a few minutes. If no tab ever opens, it also quits after a few minutes.
- On the very first launch the app downloads ffmpeg once (internet connection needed), so the first start can take longer. It is cached in the `.plumm` folder in your home directory, so later starts are fast.

---

## Troubleshooting

### Songs not downloading on Windows 11
If you are on Windows and the app is unable to save files (even in the Downloads folder), it may be due to **Windows Defender Controlled Folder Access**.

If you encounter this:
1. Open the **Start Menu**, type **"Windows Security"**, and open it.
2. Navigate to **Virus & threat protection** -> **Manage ransomware protection**.
3. If **"Controlled folder access"** is turned **On**, click on **"Allow an app through Controlled folder access"**.
4. Click **"Add an allowed app"** -> **"Browse all apps"** and select `PlumDownloader.exe` inside the extracted `PlumDownloader` folder.
5. Restart the app.

### The app will not start, or something went wrong

The app writes log files you can attach to a bug report. They are in the `.plumm/logs` folder inside your home folder:

- `plum.log`: everything the app did, with older copies rotated out automatically
- `crash.log`: only written if the app crashed hard. Relaunch the app once before copying it, because it is cleaned of personal paths on the next start

To open that folder:

- Windows: paste `%USERPROFILE%\.plumm\logs` into the File Explorer address bar
- macOS: in Finder press Cmd+Shift+G and enter `~/.plumm/logs`
- Linux: open your home folder and press Ctrl+H to show hidden files, then open `.plumm/logs`

Personal folder paths and your username are replaced automatically, but search queries and song titles are logged as typed, so skim the file before sharing it publicly.

To report a problem, open an issue on the GitHub repository and the bug report template will ask for the log.

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
git clone https://github.com/ArtificialT800/Companion-App.git
cd Companion-App

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Then open `http://localhost:7823` in your browser. When run from source, the app also prints its log to the console, and the same one-instance and close-the-tab behavior applies.

### Building a standalone executable

```bash
pyinstaller PlumDownloader.spec
```

The build produces a folder, not a single file. On Windows and Linux the output is the `dist/PlumDownloader/` folder (run the `PlumDownloader` executable inside it). On macOS it is `dist/PlumDownloader.app`. The build uses PyInstaller's one-folder mode so the app starts quickly (a single-file build would unpack itself on every launch). The `.spec` file is included in the repo and handles all `--add-data` paths and hidden imports for all three platforms.

**macOS icon**

The spec expects `icons/PlumDownloader.icns`. The GitHub Actions build generates it from a PNG on every run. For a local macOS build, create that file first (for example with `sips` and `iconutil`), or change `icon='icons/PlumDownloader.icns'` to `icon=None` in `PlumDownloader.spec`.

**Releases**

Releases are built by GitHub Actions (`.github/workflows/build.yml`) for Windows, macOS and Linux whenever a tag starting with `v` is pushed.

---

<div align="center">
Made by <a href="https://www.instagram.com/artificialt800/">Arti R</a>
</div>