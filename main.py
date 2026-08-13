#!/usr/bin/env python3
"""
YT‑FR Pro – Advanced YouTube Download Manager
Entry point: CLI, config loading, dependency checks, and main loop.
"""

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

# ----------------------- AUTO‑INSTALLER -----------------------
REQUIRED_PYTHON_PACKAGES = [
    "yt-dlp",
    "requests",
    "aiohttp",
    "Flask",
    "PyYAML",
    "cryptography",
]

def check_and_install_packages():
    """Check required Python packages and install missing ones via pip."""
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
    """Check if FFmpeg is available; if not, attempt to download (Windows) or advise."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("FFmpeg not found. Attempting auto‑install (Windows only with winget)...")
        if sys.platform == "win32":
            try:
                subprocess.run(["winget", "install", "FFmpeg"], check=True)
                print("FFmpeg installed via winget. Please restart the terminal.")
            except:
                print("Auto‑install failed. Please install FFmpeg manually from https://ffmpeg.org/")
        else:
            print("Please install FFmpeg using your package manager (e.g., apt install ffmpeg).")
        return False
    return True

def setup_environment():
    """Run all setup checks."""
    check_and_install_packages()
    check_ffmpeg()
    # Create default config if not exists
    config_path = Path("config.yaml")
    if not config_path.exists():
        default_config = {
            "concurrency": 3,
            "download_dir": "./downloads",
            "proxy": None,  # or list of proxies
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
        with open(config_path, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)
        print("Created default config.yaml. Please review and adjust.")
    else:
        print("Config file already exists.")
    print("Setup complete.")

# ----------------------- LOGGING -----------------------
def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """Configure root logger."""
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
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    # Merge with CLI overrides later
    return config

# ----------------------- RESOURCE MONITOR (stub) -----------------------
class ResourceMonitor:
    """Monitor system resources (RAM, GPU) to manage concurrency."""
    @staticmethod
    def get_memory_usage() -> float:
        """Return current RAM usage in GB."""
        import psutil
        return psutil.virtual_memory().used / (1024**3)

    @staticmethod
    def get_gpu_info() -> dict:
        """Detect GPU and memory usage (Windows only with nvidia-smi)."""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return {
                "name": pynvml.nvmlDeviceGetName(handle),
                "used": mem_info.used / (1024**3),
                "total": mem_info.total / (1024**3),
            }
        except ImportError:
            # Fallback: use nvidia-smi
            try:
                result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"],
                                        capture_output=True, text=True, check=True)
                used, total = result.stdout.strip().split(",")
                return {"used": float(used.split()[0])/1024, "total": float(total.split()[0])/1024}
            except:
                return {"used": 0, "total": 0}
        except:
            return {"used": 0, "total": 0}

# ----------------------- MAIN -----------------------
def main():
    parser = argparse.ArgumentParser(description="YT‑FR Pro Download Manager")
    parser.add_argument("--url", help="Video/playlist/channel URL")
    parser.add_argument("--format", choices=["mp4", "mp3", "mkv", "webm"], help="Output format")
    parser.add_argument("--concurrency", type=int, help="Number of parallel downloads")
    parser.add_argument("--proxy", help="Proxy URL (e.g., socks5://127.0.0.1:1080)")
    parser.add_argument("--vpn", action="store_true", help="Enable VPN mode (requires config)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--setup", action="store_true", help="Run setup (install dependencies and create config)")
    parser.add_argument("--batch", help="File with list of URLs")
    parser.add_argument("--list", help="List available formats for a URL", nargs="?")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.setup:
        setup_environment()
        sys.exit(0)

    # Load config
    config = load_config(args.config)
    # Override with CLI
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

    # Setup logging
    setup_logging(config["logging"]["level"], config["logging"].get("file"))
    logger = logging.getLogger("main")
    logger.info("Starting YT-FR Pro")

    # Resource monitor
    monitor = ResourceMonitor()
    ram_gb = monitor.get_memory_usage()
    gpu = monitor.get_gpu_info()
    logger.info(f"System: RAM used {ram_gb:.2f} GB, GPU: {gpu.get('name', 'N/A')} ({gpu.get('used',0):.2f}/{gpu.get('total',0):.2f} GB)")

    # Import core module (delayed to allow setup)
    from core import DownloadManager, QueueManager

    # Initialize manager
    manager = DownloadManager(config, monitor=monitor)
    queue = QueueManager()

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received, waiting for downloads to finish...")
        manager.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Process URLs
    urls = []
    if args.url:
        urls.append(args.url)
    if args.batch:
        with open(args.batch, "r") as f:
            urls.extend([line.strip() for line in f if line.strip()])

    if not urls:
        logger.error("No URL provided. Use --url or --batch.")
        sys.exit(1)

    for url in urls:
        queue.add_job(url, config["format"])

    # Start processing
    manager.process_queue(queue)

    logger.info("All downloads finished.")

if __name__ == "__main__":
    main()