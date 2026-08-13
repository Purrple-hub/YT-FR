#!/usr/bin/env python3
"""
auto-setup.py – Environment bootstrapper for YT‑FR Pro.
Checks Python, installs all packages, verifies FFmpeg, creates config.
"""

import sys
import os
import subprocess
import platform
import shutil
import json
import tempfile
from pathlib import Path
import importlib.util
import secrets
import yaml

REQUIRED_PYTHON_VERSION = (3, 9)
REQUIRED_PACKAGES = [
    "yt-dlp",
    "requests",
    "aiohttp",
    "Flask",
    "PyYAML",
    "cryptography",
    "psutil",
    "pynvml",
    "schedule",
    "win10toast",
]

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
    if shutil.which("ffmpeg"):
        print_ok("FFmpeg found")
        return True
    print_step("FFmpeg not found. Attempting automatic install...")
    system = platform.system()
    if system == "Windows":
        try:
            subprocess.run(["winget", "install", "FFmpeg"], check=True, capture_output=True)
            print_ok("FFmpeg installed via winget")
            return True
        except:
            print_err("winget failed. Trying manual download...")
            try:
                import requests, zipfile, io
                url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                r = requests.get(url, timeout=30)
                z = zipfile.ZipFile(io.BytesIO(r.content))
                z.extractall(tempfile.gettempdir())
                import glob
                found = glob.glob(os.path.join(tempfile.gettempdir(), "ffmpeg-*", "bin", "ffmpeg.exe"))
                if found:
                    # Copy to System32 (might need admin)
                    try:
                        shutil.copy(found[0], "C:\\Windows\\System32\\ffmpeg.exe")
                        print_ok("FFmpeg installed manually.")
                        return True
                    except PermissionError:
                        print_err("Need admin rights to copy FFmpeg. Please run as Administrator or install manually.")
                        return False
            except Exception as e:
                print_err(f"Manual install failed: {e}")
                return False
    elif system == "Darwin":
        try:
            subprocess.run(["brew", "install", "ffmpeg"], check=True)
            print_ok("FFmpeg installed via Homebrew")
            return True
        except:
            print_err("Could not install via Homebrew. Please install manually.")
            return False
    else:
        try:
            subprocess.run(["sudo", "apt", "install", "-y", "ffmpeg"], check=True)
            print_ok("FFmpeg installed via apt")
            return True
        except:
            try:
                subprocess.run(["sudo", "dnf", "install", "-y", "ffmpeg"], check=True)
                print_ok("FFmpeg installed via dnf")
                return True
            except:
                print_err("Could not install FFmpeg. Please install manually.")
                return False

def create_config():
    config_path = Path("config.yaml")
    if config_path.exists():
        print_ok("config.yaml already exists, skipping.")
        return
    print_step("Creating default config.yaml...")
    default_config = {
        "concurrency": 3,
        "download_dir": "./downloads",
        "proxy": None,
        "vpn": {"enabled": False, "command": "openvpn", "config": ""},
        "retry": {"max_attempts": 5, "backoff_factor": 2},
        "format": "mp4",
        "metadata": True,
        "subtitles": True,
        "thumbnail": True,
        "post_process": {"convert": False, "target_format": "mp4"},
        "logging": {"level": "INFO", "file": "download.log"},
        "api": {"enabled": False, "port": 5000, "api_key": secrets.token_urlsafe(16)},
        "scheduler": {"enabled": False, "cron": "0 0 * * *"},
        "subscriptions": [],
    }
    with open(config_path, "w") as f:
        yaml.dump(default_config, f, default_flow_style=False)
    print_ok("Created config.yaml with generated API key.")

def create_download_dir():
    dir_path = Path("downloads")
    if not dir_path.exists():
        dir_path.mkdir()
        print_ok("Created downloads directory.")

def main():
    print("=== YT‑FR Pro Auto‑Setup ===")
    print_step("Checking Python version...")
    check_python_version()
    print_step("Installing Python packages...")
    install_packages()
    print_step("Checking FFmpeg...")
    ffmpeg_ok = check_ffmpeg()
    if not ffmpeg_ok:
        print("WARNING: FFmpeg not installed. Conversions and thumbnails will fail.")
    print_step("Creating configuration...")
    create_config()
    create_download_dir()
    print("\n=== Setup complete ===")
    print("Run: python main.py --url <URL> --format mp4")
    print("For API server: python main.py --api")
    if not ffmpeg_ok:
        print("Please install FFmpeg manually to enable all features.")

if __name__ == "__main__":
    main()
