#!/usr/bin/env python3
"""
auto-setup.py – Environment bootstrapper for YT‑FR Pro.
Checks Python, installs packages, verifies FFmpeg, and creates config.
"""

import sys
import os
import subprocess
import platform
import shutil
import json
from pathlib import Path
import importlib.util

# ---------- Configuration ----------
REQUIRED_PYTHON_VERSION = (3, 9)
REQUIRED_PACKAGES = [
    "yt-dlp",
    "requests",
    "aiohttp",
    "Flask",
    "PyYAML",
    "cryptography",
    "psutil",      # for resource monitoring
    "pynvml",      # optional GPU monitoring
    "schedule",    # scheduler
    "win10toast",  # Windows notifications (optional)
]
FFMPEG_URLS = {
    "Windows": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "Darwin": "https://evermeet.cx/ffmpeg/ffmpeg-6.0.zip",
}
CONFIG_TEMPLATE = {
    "concurrency": 3,
    "download_dir": "./downloads",
    "proxy": None,  # or ["socks5://...", "http://..."]
    "vpn": {"enabled": False, "command": "openvpn", "config": ""},
    "retry": {"max_attempts": 5, "backoff_factor": 2},
    "format": "mp4",
    "metadata": True,
    "subtitles": True,
    "thumbnail": True,
    "post_process": {"convert": False, "target_format": "mp4"},
    "logging": {"level": "INFO", "file": "download.log"},
    "api": {"enabled": False, "port": 5000},
    "scheduler": {"enabled": False, "cron": "0 0 * * *"},
}

# ---------- Helper functions ----------
def print_step(msg):
    print(f"\n[STEP] {msg}")

def print_ok(msg):
    print(f"[OK] {msg}")

def print_err(msg):
    print(f"[ERROR] {msg}")

def check_python_version():
    if sys.version_info < REQUIRED_PYTHON_VERSION:
        print_err(f"Python {REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]} or higher required.")
        sys.exit(1)
    print_ok(f"Python version {sys.version_info.major}.{sys.version_info.minor} OK")

def install_packages():
    """Install missing Python packages via pip."""
    missing = []
    for pkg in REQUIRED_PACKAGES:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    if missing:
        print_step(f"Installing missing packages: {', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        except subprocess.CalledProcessError as e:
            print_err(f"Failed to install packages: {e}")
            sys.exit(1)
    else:
        print_ok("All required packages already installed")

def check_ffmpeg():
    """Check if ffmpeg is available; if not, try to install or guide user."""
    if shutil.which("ffmpeg"):
        print_ok("FFmpeg found")
        return True
    print_step("FFmpeg not found. Attempting automatic install...")
    system = platform.system()
    if system == "Windows":
        # Try winget
        try:
            subprocess.run(["winget", "install", "FFmpeg"], check=True, capture_output=True)
            print_ok("FFmpeg installed via winget")
            return True
        except:
            print_err("Could not install FFmpeg via winget.")
            # Provide manual download link
            print(f"Please download FFmpeg from {FFMPEG_URLS['Windows']} and add it to PATH.")
            return False
    elif system == "Darwin":
        try:
            subprocess.run(["brew", "install", "ffmpeg"], check=True)
            print_ok("FFmpeg installed via Homebrew")
            return True
        except:
            print_err("Could not install FFmpeg via Homebrew. Please install manually from https://ffmpeg.org/")
            return False
    else:  # Linux
        try:
            subprocess.run(["sudo", "apt", "install", "-y", "ffmpeg"], check=True)
            print_ok("FFmpeg installed via apt")
            return True
        except:
            print_err("Could not install FFmpeg via apt. Please install manually.")
            return False

def create_config():
    """Create default config.yaml if missing."""
    config_path = Path("config.yaml")
    if config_path.exists():
        print_ok("config.yaml already exists, skipping.")
        return
    print_step("Creating default config.yaml...")
    with open(config_path, "w") as f:
        import yaml
        yaml.dump(CONFIG_TEMPLATE, f, default_flow_style=False)
    print_ok("Created config.yaml – review and adjust as needed.")

def create_download_dir():
    """Create the download directory if not present."""
    dir_path = Path(CONFIG_TEMPLATE["download_dir"])
    if not dir_path.exists():
        dir_path.mkdir(parents=True)
        print_ok(f"Created download directory: {dir_path}")

def main():
    print("=== YT‑FR Pro Auto‑Setup ===")
    print_step("Checking Python version...")
    check_python_version()
    print_step("Installing Python packages...")
    install_packages()
    print_step("Checking FFmpeg...")
    ffmpeg_ok = check_ffmpeg()
    if not ffmpeg_ok:
        print("WARNING: FFmpeg is not installed. Video conversions and metadata embedding may fail.")
    print_step("Creating configuration...")
    create_config()
    create_download_dir()
    print("\n=== Setup complete ===")
    print("You can now run the main script:")
    print("  python main.py --url <your_url> --format mp4")
    if not ffmpeg_ok:
        print("Please install FFmpeg manually to enable all features.")

if __name__ == "__main__":
    main()