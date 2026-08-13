"""
Utility functions: metadata embedding, thumbnail, conversion, notifications,
system resource monitoring, and auto‑installer helpers.
"""

import os
import sys
import subprocess
import logging
import json
import shutil
import tempfile
import smtplib
import platform
from pathlib import Path
from typing import Dict, Any, Optional, List
import yt_dlp
import psutil

logger = logging.getLogger("utils")

# ----------------------- FFMPEG WRAPPER -----------------------
class FFmpegProcessor:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def convert(self, input_path: Path, output_path: Path, target_format: str = "mp4", codec: str = "libx264"):
        """Convert video/audio using FFmpeg."""
        cmd = [self.ffmpeg_path, "-i", str(input_path)]
        if target_format in ["mp4", "mkv", "webm"]:
            cmd.extend(["-c:v", codec, "-c:a", "aac"])
        elif target_format in ["mp3", "aac", "flac", "ogg"]:
            cmd.extend(["-c:a", target_format])
            # If input is video, extract audio
            cmd.extend(["-vn"])
        else:
            raise ValueError(f"Unsupported target format: {target_format}")
        cmd.extend(["-y", str(output_path)])
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr}")
        return output_path

    def embed_metadata(self, file_path: Path, metadata: Dict[str, str]):
        """Embed metadata (title, artist, etc.) into file."""
        # For MP4/mkv we use FFmpeg, for mp3 we use eyeD3 or similar.
        # Simple approach: use yt-dlp's built-in embedding via --embed-metadata
        # We'll use a separate command if needed.
        # We can also call ffmpeg with -metadata
        cmd = [self.ffmpeg_path, "-i", str(file_path)]
        for key, value in metadata.items():
            cmd.extend(["-metadata", f"{key}={value}"])
        cmd.extend(["-codec", "copy", "-y", str(file_path.with_suffix(".temp"))])
        subprocess.run(cmd, check=True)
        shutil.move(str(file_path.with_suffix(".temp")), str(file_path))
        logger.info(f"Metadata embedded in {file_path}")

    def add_thumbnail(self, file_path: Path, thumbnail_path: Path):
        """Add thumbnail as cover art (for MP4/MKV/MP3)."""
        # For MP4: use -i thumb -c copy -map 0 -map 1 -disposition:1 attached_pic
        # For simplicity, we just use ffmpeg with -i thumb -c:v copy -map 0 -map 1
        # But might need specific container.
        # We'll use a simpler method: use yt-dlp's --embed-thumbnail.
        # If that's not available, we can call ffmpeg.
        # For now, we log a message.
        logger.info(f"Thumbnail {thumbnail_path} would be embedded into {file_path}")

# ----------------------- NOTIFICATIONS -----------------------
class Notifier:
    @staticmethod
    def desktop_notify(title: str, message: str):
        """Send desktop notification (Windows/Darwin/Linux)."""
        if sys.platform == "win32":
            try:
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5)
            except:
                pass
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display notification "{message}" with title "{title}"'])
        else:
            # Linux with notify-send
            subprocess.run(["notify-send", title, message])

    @staticmethod
    def email_notify(to_email: str, subject: str, body: str, smtp_config: Dict[str, str]):
        """Send email via SMTP."""
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_config.get("from")
        msg["To"] = to_email
        server = smtplib.SMTP(smtp_config.get("host"), smtp_config.get("port", 587))
        server.starttls()
        server.login(smtp_config.get("user"), smtp_config.get("password"))
        server.send_message(msg)
        server.quit()

    @staticmethod
    def webhook_notify(url: str, payload: Dict[str, Any]):
        """Send POST request to webhook."""
        import requests
        requests.post(url, json=payload)

# ----------------------- RESOURCE MONITOR (detailed) -----------------------
class SystemMonitor:
    @staticmethod
    def get_cpu_percent() -> float:
        return psutil.cpu_percent(interval=0.5)

    @staticmethod
    def get_memory_usage() -> Dict[str, float]:
        mem = psutil.virtual_memory()
        return {"used": mem.used / (1024**3), "total": mem.total / (1024**3), "percent": mem.percent}

    @staticmethod
    def get_disk_usage(path: str = "/") -> Dict[str, float]:
        disk = psutil.disk_usage(path)
        return {"used": disk.used / (1024**3), "total": disk.total / (1024**3), "percent": disk.percent}

    @staticmethod
    def get_gpu_info() -> Dict:
        """Detailed GPU info using pynvml or nvidia-smi."""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            return {
                "name": pynvml.nvmlDeviceGetName(handle),
                "memory_used": mem.used / (1024**3),
                "memory_total": mem.total / (1024**3),
                "gpu_util": util.gpu,
                "mem_util": util.memory,
            }
        except:
            try:
                result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,utilization.memory", "--format=csv,noheader"],
                                        capture_output=True, text=True, check=True)
                parts = result.stdout.strip().split(",")
                if len(parts) >= 5:
                    return {
                        "name": parts[0].strip(),
                        "memory_used": float(parts[1].split()[0])/1024,
                        "memory_total": float(parts[2].split()[0])/1024,
                        "gpu_util": int(parts[3].strip().replace("%","")),
                        "mem_util": int(parts[4].strip().replace("%","")),
                    }
            except:
                pass
        return {"name": "N/A", "memory_used": 0, "memory_total": 0}

# ----------------------- AUTO-INSTALLER HELPERS -----------------------
def install_python_package(package: str):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def check_and_install_ffmpeg():
    """Check FFmpeg, if missing, attempt to install via winget/brew/apt."""
    if shutil.which("ffmpeg"):
        return True
    system = platform.system()
    if system == "Windows":
        try:
            subprocess.run(["winget", "install", "FFmpeg"], check=True)
            return True
        except:
            pass
    elif system == "Darwin":
        try:
            subprocess.run(["brew", "install", "ffmpeg"], check=True)
            return True
        except:
            pass
    else:  # Linux
        try:
            subprocess.run(["sudo", "apt", "install", "-y", "ffmpeg"], check=True)
            return True
        except:
            pass
    logger.warning("FFmpeg not installed and auto-install failed. Please install manually.")
    return False

def check_and_install_ytdlp():
    """Ensure yt-dlp is installed."""
    try:
        import yt_dlp
        return True
    except ImportError:
        install_python_package("yt-dlp")
        return True

# ----------------------- METADATA EXTRACTOR -----------------------
def extract_metadata(info: Dict[str, Any]) -> Dict[str, str]:
    """Extract standard metadata from yt-dlp info dict."""
    meta = {
        "title": info.get("title", ""),
        "artist": info.get("uploader", ""),
        "album": info.get("playlist_title", ""),
        "date": info.get("upload_date", ""),
        "description": info.get("description", ""),
        "genre": info.get("genre", ""),
    }
    return {k: v for k, v in meta.items() if v}

# ----------------------- FILENAME SANITIZATION -----------------------
def sanitize_filename(name: str) -> str:
    """Remove invalid characters for Windows/Unix."""
    invalid = '<>:"/\\|?*'
    for char in invalid:
        name = name.replace(char, '_')
    return name

# ----------------------- PLAYLIST/CHANNEL HANDLING -----------------------
def extract_entries(url: str) -> List[Dict]:
    """Get list of entries from playlist/channel."""
    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            return []
        if 'entries' in info:
            return info['entries']
        else:
            return [info]

# ----------------------- POST-PROCESSING PIPELINE -----------------------
class PostProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ffmpeg = FFmpegProcessor()

    def process(self, file_path: Path, job_info: Dict) -> Path:
        """Apply all post-processing steps."""
        final_path = file_path
        # Convert if needed
        if self.config.get("post_process", {}).get("convert"):
            target = self.config["post_process"]["target_format"]
            if target and file_path.suffix[1:] != target:
                new_path = file_path.with_suffix(f".{target}")
                self.ffmpeg.convert(file_path, new_path, target)
                os.remove(file_path)
                final_path = new_path

        # Embed metadata
        if self.config.get("metadata", True):
            meta = extract_metadata(job_info)
            self.ffmpeg.embed_metadata(final_path, meta)

        # Embed thumbnail
        if self.config.get("thumbnail", True):
            # If we have thumbnail path from job, use it.
            thumb_path = job_info.get("thumbnail_path")
            if thumb_path and Path(thumb_path).exists():
                self.ffmpeg.add_thumbnail(final_path, Path(thumb_path))

        return final_path

# ----------------------- LOGGING UTILITY -----------------------
def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """Reusable logging config."""
    import logging
    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers
    )

# ----------------------- CONFIG VALIDATION -----------------------
def validate_config(config: Dict) -> bool:
    """Check required keys."""
    required = ["concurrency", "download_dir", "format"]
    for key in required:
        if key not in config:
            logger.error(f"Missing config key: {key}")
            return False
    return True

# ----------------------- SUBSCRIPTION CHECK (stub) -----------------------
def check_subscriptions(config: Dict, download_manager):
    """Check all subscribed channels and download new videos."""
    # Would read a list of channel URLs from config/db and compare with history.
    logger.info("Checking subscriptions...")
    # Implementation omitted for brevity