# TeleTurbo

**TeleTurbo** is a Windows GUI tool for downloading videos from Telegram (channels, groups, private chats) with concurrent downloads and "Protect Content" bypass.

## Features

- **Telegram Desktop-style UI** — sidebar nav, dark/light mode, card preview, toast notifications
- **Protect Content bypass** — uses MTProto directly; the server always returns file bytes regardless of the restriction flag
- **Concurrent downloads** — 3 workers by default, adjustable 1–10, avoids FloodWait
- **Pause/Resume** — `.part` files track progress, resume from where it stopped
- **Link import** — paste `t.me/channel/id` or `t.me/c/CHANNEL_ID/id` links to download directly
- **Batch group/channel scan** — select multiple groups, scan for videos with a configurable message limit
- **Progress bar + speed + ETA** — real-time estimated time remaining
- **Filter tabs** — All / Downloading / Completed / Failed with live counts
- **Context menu** — right-click → Start / Pause / Remove / Open Folder
- **Keyboard shortcuts** — `Ctrl+G` Groups, `Ctrl+D` Downloads, `Space` toggle checkbox, `Del` remove
- **Thumbnail preview** — view thumbnail + file info in the right panel
- **Auto-login** — session persistence, automatic login on next launch
- **Theme toggle** — switch dark/light mode, persisted in `config.json`

## Requirements

- Windows 10/11
- Python 3.10+
- Telegram account + **API ID & API Hash** (get from [my.telegram.org/apps](https://my.telegram.org/apps))

## Installation

### 1. Clone or download

```bash
git clone https://github.com/yourname/teleturbo.git
cd teleturbo
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run

```bash
python main.py
```

## Usage guide

### Step 1: Enter API credentials

1. Go to [my.telegram.org/apps](https://my.telegram.org/apps), log in, create a new app
2. Copy the **API ID** and **API Hash**
3. Paste them into the corresponding fields in the Login tab, click **Save**

### Step 2: Sign in

1. Enter your phone number (international format: `+84912345678` or `84912345678`)
2. Click **Send Code**
3. Enter the OTP sent to your Telegram, click **Sign In**
4. (If 2FA is enabled) Enter your 2FA password

> The session is saved automatically — next launch will auto-login.

### Step 3: Select groups/channels

1. Go to the **Groups** tab (or `Ctrl+G`)
2. Click **Refresh** to load your dialogs
3. Check the groups/channels you want to scan (click the checkbox column)
4. Click **Fetch Videos** to find all videos

### Step 4: Download videos

1. After scanning completes, the app switches to the **Downloads** tab
2. Videos are checked by default
3. Click **Start Checked** (or right-click → Start)
4. Monitor progress: progress bar, speed, ETA in the preview panel
5. Completed files are saved to `downloads/<Group Name>/`

### Import a single link

1. Copy a link: `https://t.me/username/123` or `https://t.me/c/1234567890/123`
2. Paste it into the **Link** field in the Downloads tab
3. Click **Fetch** — the video is added to the list

## Configuration

`config.json` is auto-created in the working directory:

```json
{
  "api_id": 12345,
  "api_hash": "your_api_hash_here",
  "phone": "+84912345678",
  "download_dir": "downloads",
  "max_concurrent": 3,
  "max_messages_per_group": 200,
  "dark_mode": true
}
```

| Key | Description | Default |
|-----|-------------|---------|
| `api_id` | App ID from my.telegram.org | `0` |
| `api_hash` | App Hash from my.telegram.org | `""` |
| `phone` | Phone number for login | `""` |
| `download_dir` | Download output directory | `"downloads"` |
| `max_concurrent` | Concurrent download workers (1–10) | `3` |
| `max_messages_per_group` | Max messages to scan per group | `200` |
| `dark_mode` | Dark theme (`true`) / light theme (`false`) | `true` |

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+L` | Switch to Login tab |
| `Ctrl+G` | Switch to Groups tab |
| `Ctrl+D` | Switch to Downloads tab |
| `Delete` | Remove selected items |
| `Space` | Toggle checkbox (Groups / Downloads) |
| `Right-click` | Context menu on download items |

## Build standalone .exe

Run the build script (requires PyInstaller):

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

The `.exe` is output to `dist\TeleTurbo.exe`.

> Copy `TeleTurbo.exe` to an empty folder before running — it will create `sessions/` and `config.json` in the same directory on first launch.

## Directory structure

```
teleturbo/
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
├── build.ps1                # Build script (PyInstaller)
├── config.json              # Settings (API key, preferences)
├── app/
│   ├── __init__.py
│   ├── gui.py               # Tkinter GUI (~1600 lines)
│   ├── client.py            # Telethon wrapper (auth, download)
│   ├── downloader.py        # Queue + workers + resume
│   └── config.py            # Read/write config.json
├── sessions/                # Saved Telegram sessions (auto-created)
├── downloads/               # Downloaded videos (default)
├── cache/
│   └── thumbnails/          # Thumbnail cache
└── assets/                  # (reserved for icons, resources)
```

## Architecture

- **`main.py`** — creates a background asyncio event loop thread, runs GUI on the main thread
- **`app/gui.py`** — Tkinter, 3-section layout (Login / Groups / Downloads), sidebar navigation, async integration
- **`app/client.py`** — `TGClient` wrapping Telethon: auth, dialog listing, video detection, resumable download, thumbnails, link resolver
- **`app/downloader.py`** — `DownloadQueue` managing queue, worker pool, progress callbacks, `.part` file resume
- **`app/config.py`** — load/save JSON configuration

**Download flow:**
```
User clicks Start
  → GUI pushes items into DownloadQueue
  → Async workers download chunks via iter_download(offset=...)
  → Progress callback updates speed + progress + ETA
  → GUI updates treeview every 150ms (throttled)
  → Complete: rename .part → final file
```

**Resume flow:**
```
Active download saves to .part file
  → On restart: check for existing .part → read size
  → iter_download(message, offset=existing_size)
  → Append chunks to .part
  → On success: rename .part to final filename
```

## FAQ

**Q: Can "Protect Content" block downloads?**  
A: No. Protect Content is client-side — it only blocks forwarding/screenshots inside official apps. Telethon uses MTProto directly, so the server always returns the file.

**Q: Slow downloads / FloodWaitError?**  
A: Reduce `max_concurrent` to 1 or 2. Telegram throttles bandwidth for free accounts.

**Q: Does Premium download faster?**  
A: No — bandwidth throttling is server-side; Premium doesn't unlock faster downloads.

**Q: "AuthRestartError"?**  
A: The app auto-retries by disconnecting and reconnecting. If it persists, delete the session file in `sessions/` and log in again.

**Q: Downloaded file won't open?**  
A: Check the file size. If it's smaller than expected, the download was interrupted (FloodWait). Delete the `.part` file and re-download.

## License

MIT
