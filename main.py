import argparse
import sys
import os
import logging
import signal
import yaml
import subprocess
import importlib
import pkg_resources
from pathlib import Path
from typing import Dict, Any, Optional
import time
import threading
import json
import secrets
from flask import Flask, request, jsonify, abort
import psutil
import shutil
import tempfile

# ----------------------- AUTO‑INSTALLER -----------------------
REQUIRED_PYTHON_PACKAGES = [
    "yt-dlp",
    "requests",
    "aiohttp",
    "Flask",
    "PyYAML",
    "cryptography",
    "psutil",
    "pynvml",          # optional but recommended
    "schedule",
    "win10toast",      # optional
]

def check_and_install_packages():
    missing = []
    for pkg in REQUIRED_PYTHON_PACKAGES:
        try:
            pkg_resources.get_distribution(pkg)
        except pkg_resources.DistributionNotFound:
            missing.append(pkg)
    if missing:
        print(f"Missing Python packages: {', '.join(missing)}. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("Packages installed successfully.")

def check_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    print("FFmpeg not found. Attempting auto‑install...")
    system = platform.system()
    if system == "Windows":
        try:
            subprocess.run(["winget", "install", "FFmpeg"], check=True)
            print("FFmpeg installed via winget.")
            return True
        except:
            # Fallback: download and extract from gyan.dev
            try:
                import requests, zipfile, io
                url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                r = requests.get(url)
                z = zipfile.ZipFile(io.BytesIO(r.content))
                z.extractall(tempfile.gettempdir())
                # Find ffmpeg.exe and copy to a directory in PATH or add to PATH
                extracted = Path(tempfile.gettempdir()) / "ffmpeg-*" / "bin" / "ffmpeg.exe"
                import glob
                found = glob.glob(str(extracted))
                if found:
                    shutil.copy(found[0], "C:\\Windows\\System32\\ffmpeg.exe")  # requires admin
                    print("FFmpeg installed manually (may require admin).")
                    return True
            except Exception as e:
                print(f"Manual FFmpeg install failed: {e}")
                return False
    elif system == "Darwin":
        try:
            subprocess.run(["brew", "install", "ffmpeg"], check=True)
            return True
        except:
            print("Please install FFmpeg manually via https://ffmpeg.org/")
            return False
    else:  # Linux
        try:
            subprocess.run(["sudo", "apt", "install", "-y", "ffmpeg"], check=True)
            return True
        except:
            try:
                subprocess.run(["sudo", "dnf", "install", "-y", "ffmpeg"], check=True)
                return True
            except:
                print("Please install FFmpeg manually (e.g., 'sudo apt install ffmpeg').")
                return False

def setup_environment():
    check_and_install_packages()
    ffmpeg_ok = check_ffmpeg()
    config_path = Path("config.yaml")
    if not config_path.exists():
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
        }
        with open(config_path, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)
        print("Created default config.yaml. API key is generated; keep it safe.")
    else:
        print("Config file already exists.")
    if not ffmpeg_ok:
        print("WARNING: FFmpeg not installed – video conversions and metadata will fail.")
    print("Setup complete.")

# ----------------------- LOGGING -----------------------
def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers
    )

# ----------------------- CONFIG LOADER -----------------------
def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config

# ----------------------- RESOURCE MONITOR (full) -----------------------
class ResourceMonitor:
    @staticmethod
    def get_memory_usage() -> float:
        return psutil.virtual_memory().used / (1024**3)

    @staticmethod
    def get_gpu_info() -> dict:
        # Try NVIDIA first
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            return {
                "name": pynvml.nvmlDeviceGetName(handle).decode(),
                "used": mem.used / (1024**3),
                "total": mem.total / (1024**3),
                "util": util.gpu,
            }
        except:
            pass
        # Try AMD via rocm-smi
        try:
            result = subprocess.run(["rocm-smi", "--showuse", "--showmemuse"], capture_output=True, text=True)
            # Parse output...
            # Simplified: just return a dict
            return {"name": "AMD", "used": 0, "total": 0}
        except:
            pass
        # Try Intel via intel-gpu-tools
        try:
            result = subprocess.run(["intel_gpu_top", "-J"], capture_output=True, text=True)
            data = json.loads(result.stdout)
            return {"name": "Intel", "used": 0, "total": 0}
        except:
            pass
        # Fallback: use nvidia-smi if available
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader"], capture_output=True, text=True, check=True)
            parts = result.stdout.strip().split(",")
            if len(parts) >= 4:
                return {
                    "name": parts[0].strip(),
                    "used": float(parts[1].split()[0])/1024,
                    "total": float(parts[2].split()[0])/1024,
                    "util": int(parts[3].strip().replace("%","")),
                }
        except:
            pass
        return {"name": "N/A", "used": 0, "total": 0}

# ----------------------- MAIN -----------------------
def main():
    parser = argparse.ArgumentParser(description="YT‑FR Pro Download Manager")
    parser.add_argument("--url", help="Video/playlist/channel URL")
    parser.add_argument("--format", choices=["mp4", "mp3", "mkv", "webm"], help="Output format")
    parser.add_argument("--concurrency", type=int, help="Number of parallel downloads")
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument("--vpn", action="store_true", help="Enable VPN mode (requires config)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--setup", action="store_true", help="Run setup (install dependencies and create config)")
    parser.add_argument("--batch", help="File with list of URLs")
    parser.add_argument("--list", help="List available formats for a URL", nargs="?")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--api", action="store_true", help="Start REST API server")
    args = parser.parse_args()

    if args.setup:
        setup_environment()
        sys.exit(0)

    config = load_config(args.config)
    if args.url:
        config["url"] = args.url
    if args.format:
        config["format"] = args.format
    if args.concurrency:
        config["concurrency"] = args.concurrency
    if args.proxy:
        config["proxy"] = args.proxy
    if args.vpn:
        config["vpn"]["enabled"] = True
    if args.debug:
        config["logging"]["level"] = "DEBUG"

    setup_logging(config["logging"]["level"], config["logging"].get("file"))
    logger = logging.getLogger("main")
    logger.info("Starting YT‑FR Pro")

    # Resource monitor
    monitor = ResourceMonitor()
    ram_gb = monitor.get_memory_usage()
    gpu = monitor.get_gpu_info()
    logger.info(f"System: RAM used {ram_gb:.2f} GB, GPU: {gpu.get('name', 'N/A')} ({gpu.get('used',0):.2f}/{gpu.get('total',0):.2f} GB)")

    from core import DownloadManager, QueueManager, VPNManager, ProxyManager, start_api
    from utils import SystemMonitor, PostProcessor, Notifier

    manager = DownloadManager(config, monitor=monitor)
    queue = QueueManager()

    # VPN killswitch
    vpn = VPNManager(config)
    vpn.killswitch_callback = manager.pause
    if config["vpn"]["enabled"]:
        vpn.connect()

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received, waiting for downloads to finish...")
        manager.shutdown()
        vpn.disconnect()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    urls = []
    if args.url:
        urls.append(args.url)
    if args.batch:
        with open(args.batch, "r") as f:
            urls.extend([line.strip() for line in f if line.strip()])

    if not urls and not args.api:
        logger.error("No URL provided. Use --url, --batch, or start API with --api.")
        sys.exit(1)

    # If API mode, start server in separate thread
    if args.api:
        api_thread = threading.Thread(target=start_api, args=(config, queue, manager), daemon=True)
        api_thread.start()
        logger.info(f"API server started on port {config['api'].get('port', 5000)}")
        # Keep main thread alive
        while True:
            time.sleep(1)

    for url in urls:
        queue.add_job(url, config["format"])

    manager.process_queue(queue)
    logger.info("All downloads finished.")

if __name__ == "__main__":
    main()
