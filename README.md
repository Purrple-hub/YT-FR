# YT‑FR Pro

**Advanced YouTube Download Manager with API, VPN Support, and Resource Monitoring**

[![License: CC0-1.0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg)](http://creativecommons.org/publicdomain/zero/1.0/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

> **⚠️ Important**: This project is intended for educational and personal use only. Please respect copyright laws and YouTube's Terms of Service when using this tool.

---

## 📋 Project Description

YT‑FR Pro is a feature‑rich, Python‑based YouTube download manager that goes far beyond a simple CLI tool. Built with concurrency, resilience, and automation in mind, it supports:

- **Batch downloading** of videos, playlists, and entire channels
- **REST API** with API‑key authentication for remote control
- **VPN integration** with automatic kill‑switch on disconnect
- **Proxy rotation** with health checks
- **Smart resource monitoring** that dynamically adjusts concurrency based on RAM usage
- **Post‑processing** – format conversion, metadata embedding, and thumbnail attachment
- **Scheduled subscriptions** for automatic channel updates
- **Desktop, email, and webhook notifications**

The project is structured as a production‑ready application with a modular architecture, making it easy to extend and customize.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🚀 **Concurrent Downloads** | Download multiple videos in parallel with configurable concurrency |
| 🔁 **Smart Retry Logic** | Exponential backoff with proxy rotation on failure |
| 🌐 **Proxy Management** | Rotating proxy support with automatic health checking |
| 🔒 **VPN Integration** | OpenVPN support with kill‑switch to pause downloads on disconnect |
| 📡 **REST API** | Full API with key authentication – submit, pause, resume, and monitor jobs |
| 📊 **Resource Monitoring** | Tracks CPU, RAM, disk, and GPU (NVIDIA/AMD/Intel) usage; auto‑adjusts concurrency |
| 🎬 **Post‑Processing** | Convert formats, embed metadata, attach thumbnails via FFmpeg |
| 📅 **Scheduler** | Cron‑like scheduling for automatic subscription checks |
| 🔔 **Notifications** | Desktop (Windows/macOS/Linux), email, and webhook alerts |
| 💾 **Download History** | SQLite database to avoid re‑downloading content |
| 🧪 **Self‑Test Suite** | Built‑in `test.py` to verify your environment and dependencies |

---

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Purrple-hub/YT-FR.git
cd YT-FR

# 2. Run the auto‑setup (installs dependencies, FFmpeg, and creates config)
python auto-setup.py

# 3. Download a video
python main.py --url "https://youtu.be/..." --format mp4

# 4. (Optional) Start the API server
python main.py --api
```

---

## 📦 Installation

### Prerequisites

- **Python 3.9** or higher
- **FFmpeg** (auto‑installed by `auto-setup.py` on most platforms)
- **pip** (latest)

### Automatic Setup (Recommended)

The included `auto-setup.py` handles everything:

```bash
python auto-setup.py
```

It will:
- ✅ Check your Python version
- ✅ Install all required packages (`yt-dlp`, `Flask`, `PyYAML`, `psutil`, etc.)
- ✅ Install FFmpeg (via winget, Homebrew, apt, or manual fallback)
- ✅ Generate a default `config.yaml` with a secure API key
- ✅ Create the `downloads/` directory

### Manual Installation

```bash
pip install -r requirements.txt   # or install individually:
pip install yt-dlp requests aiohttp Flask PyYAML cryptography psutil pynvml schedule win10toast
```

Ensure FFmpeg is in your `PATH` – download from [ffmpeg.org](https://ffmpeg.org/).

---

## ⚙️ Configuration

YT‑FR Pro is configured via `config.yaml`. A default file is generated automatically on first run.

```yaml
concurrency: 3                   # Parallel downloads
download_dir: ./downloads        # Where files are saved
proxy: null                      # Single proxy or list: ["http://...", "socks5://..."]
format: mp4                      # Default output: mp4, mp3, mkv, webm
metadata: true                   # Embed metadata (title, uploader, etc.)
subtitles: true                  # Download subtitles
thumbnail: true                  # Attach thumbnail as cover art

vpn:
  enabled: false
  command: openvpn
  config: /path/to/config.ovpn

retry:
  max_attempts: 5
  backoff_factor: 2

post_process:
  convert: false
  target_format: mp4

logging:
  level: INFO
  file: download.log

api:
  enabled: false
  port: 5000
  api_key: "your-secure-key-here"   # Auto‑generated

scheduler:
  enabled: false
  cron: "0 0 * * *"                  # Daily at midnight

subscriptions: []                    # List of channel/playlist URLs
```

> **Security**: The `api_key` is auto‑generated using `secrets.token_urlsafe(16)` – keep it safe!

---

## 💻 Usage Examples

### Command‑Line Interface

```bash
# Download a single video in MP4
python main.py --url "https://youtu.be/dQw4w9WgXcQ"

# Download as MP3 (audio only)
python main.py --url "https://youtu.be/..." --format mp3

# Download a playlist or channel
python main.py --url "https://youtube.com/playlist?list=..."

# Batch download from a file (one URL per line)
python main.py --batch urls.txt

# Use a proxy
python main.py --url "..." --proxy "socks5://127.0.0.1:1080"

# Enable VPN mode
python main.py --url "..." --vpn

# Set concurrency (parallel downloads)
python main.py --url "..." --concurrency 5

# Debug logging
python main.py --url "..." --debug
```

### API Server

Start the API server:

```bash
python main.py --api
```

Then interact via HTTP:

```bash
# Check status
curl -H "X-API-Key: your-key" http://localhost:5000/status

# Submit a download
curl -X POST -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtu.be/...", "format": "mp4"}' \
  http://localhost:5000/submit

# Pause / resume
curl -X POST -H "X-API-Key: your-key" http://localhost:5000/pause
curl -X POST -H "X-API-Key: your-key" http://localhost:5000/resume

# List available formats for a URL
curl -H "X-API-Key: your-key" "http://localhost:5000/list?url=https://youtu.be/..."

# View download history
curl -H "X-API-Key: your-key" http://localhost:5000/history
```

### Using as a Library

```python
from core import DownloadManager, QueueManager
from main import load_config

config = load_config("config.yaml")
queue = QueueManager()
manager = DownloadManager(config)

queue.add_job("https://youtu.be/...", "mp4")
manager.process_queue(queue)
```

---

## 🧪 Running Tests

YT‑FR Pro includes a comprehensive test suite (`test.py`) that validates your environment and core functionality.

```bash
python test.py
```

The test suite checks:
- ✅ Module imports (`main`, `core`, `utils`)
- ✅ Python version (≥3.9)
- ✅ CPU cores, RAM, disk space, GPU info
- ✅ FFmpeg availability
- ✅ Network connectivity
- ✅ Config loading
- ✅ Proxy rotation
- ✅ FFmpeg conversion
- ✅ Queue manager
- ✅ Resource monitor
- ✅ Download manager initialisation

---

## 📝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork** the repository
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit your changes** (`git commit -m 'Add some amazing feature'`)
4. **Push** (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

Please ensure your code passes the test suite (`python test.py`) and follows the existing style.

---

## 📄 License

This project is dedicated to the public domain under the **Creative Commons CC0 1.0 Universal License**. You can copy, modify, distribute, and use the work, even for commercial purposes, all without asking permission.

See the [LICENSE](LICENSE) file for full details.

---

## 😫 Flaws

Like any tool, YT‑FR Pro has its limitations:

| Issue | Description |
|-------|-------------|
| 🧠 **AI‑Generated Core** | The majority of the code was generated by AI (DeepSeek and Gemini), which means some logic may be overly verbose or lack human nuance |
| 🔧 **VPN Kill‑Switch** | The kill‑switch relies on process monitoring; network‑level kill‑switch (e.g., iptables) is not implemented |
| 📦 **FFmpeg Installation** | The auto‑installer may fail on some systems; manual installation may be required |
| 📊 **GPU Monitoring** | AMD and Intel GPU detection is rudimentary and may not report accurate metrics |
| ⏱️ **Scheduler** | Currently only supports daily execution at midnight; more granular cron support is planned |
| 🔌 **Cancel API** | The `/cancel` endpoint is a stub – cancelling individual jobs is not yet implemented |
| 🧪 **Test Coverage** | Unit tests are limited; the test suite focuses on integration/environment checks |

---

## 👻 Human Made or AI?

**Analysis: This project is predominantly AI‑generated, with some human refinement.**

### Evidence for AI Generation

- **Commit History**: The author explicitly states in commit `8030bfd`: *"its not that bad but its def made by AI, not everything, i did make the main.py and auto-setup.py and half of the test.py, the AI that made the actual project is Deepseek and Gemini."*

- **Code Patterns**: The code exhibits hallmarks of AI‑generated output:
  - **Over‑documentation**: Every function, class, and module has verbose docstrings – a common AI trait
  - **Redundant imports**: Some modules import packages that aren't used (e.g., `aiohttp` imported but never utilised)
  - **Generic structure**: The architecture follows a textbook pattern without the subtle optimisations a human would add
  - **Conservative error handling**: Exception handling is broad (`except Exception`) rather than specific

- **Config Generation**: The auto‑generated `config.yaml` includes every possible option with default values – comprehensive but generic

### Evidence of Human Touch

- **`main.py` and `auto-setup.py`**: The author claims to have written these personally, and they do show more nuanced error handling and user‑friendly messages
- **`test.py`**: Half of this file was human‑written, and it includes thoughtful device capability checks
- **Commit messages**: The commit history shows a human refining the AI‑generated code (e.g., *"Refactor test.py for improved readability and structure"*)

### Verdict

**AI‑Generated Core with Human Polish** – The foundation (core logic, utilities, API endpoints) was produced by AI, but the developer has actively refined the entry points, setup scripts, and test suite to make the project actually usable.

**Estimated AI Contribution**: ~75–80%  
**Estimated Human Contribution**: ~20–25%

---

## 📌 Use Cases

### 1. **Content Creator Backup**
Creators can automatically back up their own channels or favourite creators, ensuring they always have local copies of their content.

### 2. **Media Server Integration**
Use the API to integrate with media servers (Plex, Jellyfin) – submit downloads remotely and have them automatically added to your library.

### 3. **Offline Playlist Curation**
Curate offline playlists for road trips, flights, or areas with limited internet. The batch mode and subscription scheduler make this effortless.

### 4. **Educational Resource Aggregation**
Educators and students can bulk‑download educational playlists for offline study, with metadata preserving original uploader and description.

### 5. **Automated Channel Monitoring**
Set up the scheduler to monitor specific channels and automatically download new uploads – ideal for news monitoring or content archival.

---

## 📊 Quality Score

| Category | Score (out of 100) | Notes |
|----------|-------------------|-------|
| **Functionality** | 85 | Core features work well; VPN kill‑switch and API are solid |
| **Code Quality** | 70 | AI‑generated code is functional but lacks human elegance; some redundancy |
| **Documentation** | 75 | Good docstrings and this README; missing inline explanations in complex sections |
| **Test Coverage** | 60 | Environment checks are comprehensive; unit tests are lacking |
| **Error Handling** | 65 | Broad exception catching; could be more specific |
| **Security** | 80 | API key auth, but no rate limiting or HTTPS enforcement |
| **Maintainability** | 70 | Modular structure helps; AI code can be hard to refactor |
| **Performance** | 75 | Concurrent downloads work well; resource monitoring adds overhead |
| **User Experience** | 80 | Auto‑setup and CLI are intuitive; API is well‑designed |
| **Innovation** | 65 | Combines existing tools (yt‑dlp, FFmpeg) effectively; no novel algorithms |

### Overall: **72 / 100**

A solid, functional tool that works well for its intended purpose. The AI‑generated foundation is competent, and the human contributions have made it genuinely usable. With some refinement – especially in testing, error handling, and code elegance – this could easily reach 85+.

---

*Built with 💜 by [Purrple‑hub](https://github.com/Purrple-hub) – and a little help from DeepSeek & Gemini.*
