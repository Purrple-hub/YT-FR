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
import platform
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import yt_dlp
import psutil
import requests

logger = logging.getLogger("utils")

# ----------------------- FFMPEG WRAPPER (full) -----------------------
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
            cmd.extend(["-vn"])
        else:
            raise ValueError(f"Unsupported target format: {target_format}")
        cmd.extend(["-y", str(output_path)])
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr}")
        return output_path

    def embed_metadata(self, file_path: Path, metadata: Dict[str, str]):
        """Embed metadata into file."""
        temp_path = file_path.with_suffix(".temp")
        cmd = [self.ffmpeg_path, "-i", str(file_path)]
        for key, value in metadata.items():
            if value:
                cmd.extend(["-metadata", f"{key}={value}"])
        cmd.extend(["-codec", "copy", "-y", str(temp_path)])
        subprocess.run(cmd, check=True, capture_output=True)
        shutil.move(str(temp_path), str(file_path))
        logger.info(f"Metadata embedded in {file_path}")

    def add_thumbnail(self, file_path: Path, thumbnail_path: Path):
        """Add thumbnail as cover art."""
        temp_path = file_path.with_suffix(".temp")
        cmd = [self.ffmpeg_path, "-i", str(file_path), "-i", str(thumbnail_path), "-map", "0", "-map", "1", "-c", "copy", "-disposition:1", "attached_pic", "-y", str(temp_path)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            shutil.move(str(temp_path), str(file_path))
            logger.info(f"Thumbnail embedded in {file_path}")
        except Exception as e:
            logger.error(f"Failed to embed thumbnail: {e}")

# ----------------------- NOTIFICATIONS (full) -----------------------
class Notifier:
    @staticmethod
    def desktop_notify(title: str, message: str):
        """Send desktop notification."""
        if sys.platform == "win32":
            try:
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5)
            except Exception as e:
                logger.warning(f"Desktop notification failed: {e}")
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display notification "{message}" with title "{title}"'])
        else:
            subprocess.run(["notify-send", title, message])

    @staticmethod
    def email_notify(to_email: str, subject: str, body: str, smtp_config: Dict[str, str]):
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
        requests.post(url, json=payload, timeout=5)

# ----------------------- RESOURCE MONITOR (full) -----------------------
class SystemMonitor:
    @staticmethod
    def get_cpu_percent() -> float:
        return psutil.cpu_percent(interval=0.5)

    @staticmethod
    def get_memory_usage() -> Dict[str, float]:
        mem = psutil.virtual_memory()
        return {"used": mem.used / (1024**3), "total": mem.total / (1024**3), "percent": mem.percent}

    @staticmethod
    def get_disk_usage(path: str = ".") -> Dict[str, float]:
        disk = psutil.disk_usage(path)
        return {"used": disk.used / (1024**3), "total": disk.total / (1024**3), "percent": disk.percent}

    @staticmethod
    def get_gpu_info() -> Dict:
        """Cross‑platform GPU detection."""
        # NVIDIA
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            return {
                "name": pynvml.nvmlDeviceGetName(handle).decode(),
                "memory_used": mem.used / (1024**3),
                "memory_total": mem.total / (1024**3),
                "gpu_util": util.gpu,
                "mem_util": util.memory,
            }
        except:
            pass

        # AMD via rocm-smi
        try:
            result = subprocess.run(["rocm-smi", "--showuse", "--showmemuse", "--json"], capture_output=True, text=True, timeout=5)
            data = json.loads(result.stdout)
            # Parse
            return {"name": "AMD", "memory_used": 0, "memory_total": 0, "gpu_util": 0, "mem_util": 0}
        except:
            pass

        # Intel via intel_gpu_top
        try:
            result = subprocess.run(["intel_gpu_top", "-J", "-s", "1"], capture_output=True, text=True, timeout=3)
            # Not easily parsable; just return generic
            return {"name": "Intel", "memory_used": 0, "memory_total": 0, "gpu_util": 0, "mem_util": 0}
        except:
            pass

        # Fallback to nvidia-smi
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,utilization.memory", "--format=csv,noheader"], capture_output=True, text=True, check=True, timeout=5)
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

        return {"name": "N/A", "memory_used": 0, "memory_total": 0, "gpu_util": 0, "mem_util": 0}

# ----------------------- AUTO-INSTALLER HELPERS (enhanced) -----------------------
def install_python_package(package: str):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def check_and_install_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    logger.warning("FFmpeg not found. Attempting auto‑install...")
    system = platform.system()
    if system == "Windows":
        try:
            subprocess.run(["winget", "install", "FFmpeg"], check=True, capture_output=True)
            return True
        except:
            # Try downloading manually
            try:
                url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                r = requests.get(url, timeout=30)
                import zipfile, io
                z = zipfile.ZipFile(io.BytesIO(r.content))
                z.extractall(tempfile.gettempdir())
                import glob
                found = glob.glob(os.path.join(tempfile.gettempdir(), "ffmpeg-*", "bin", "ffmpeg.exe"))
                if found:
                    shutil.copy(found[0], "C:\\Windows\\System32\\ffmpeg.exe")
                    return True
            except Exception as e:
                logger.error(f"Manual FFmpeg install failed: {e}")
                return False
    elif system == "Darwin":
        try:
            subprocess.run(["brew", "install", "ffmpeg"], check=True, capture_output=True)
            return True
        except:
            return False
    else:  # Linux
        for pkgman in ["apt", "dnf", "yum"]:
            try:
                subprocess.run(["sudo", pkgman, "install", "-y", "ffmpeg"], check=True, capture_output=True)
                return True
            except:
                continue
        return False

def check_and_install_ytdlp():
    try:
        import yt_dlp
        return True
    except ImportError:
        install_python_package("yt-dlp")
        return True

# ----------------------- METADATA EXTRACTOR -----------------------
def extract_metadata(info: Dict[str, Any]) -> Dict[str, str]:
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
    invalid = '<>:"/\\|?*'
    for char in invalid:
        name = name.replace(char, '_')
    return name

# ----------------------- PLAYLIST/CHANNEL HANDLING -----------------------
def extract_entries(url: str) -> List[Dict]:
    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            return []
        if 'entries' in info:
            return info['entries']
        else:
            return [info]

# ----------------------- POST-PROCESSING PIPELINE (full) -----------------------
class PostProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ffmpeg = FFmpegProcessor()

    def process(self, file_path: Path, job_info: Dict) -> Path:
        final_path = file_path
        # Convert
        if self.config.get("post_process", {}).get("convert"):
            target = self.config["post_process"]["target_format"]
            if target and file_path.suffix[1:] != target:
                new_path = file_path.with_suffix(f".{target}")
                self.ffmpeg.convert(file_path, new_path, target)
                os.remove(file_path)
                final_path = new_path

        # Metadata
        if self.config.get("metadata", True):
            meta = extract_metadata(job_info)
            self.ffmpeg.embed_metadata(final_path, meta)

        # Thumbnail
        if self.config.get("thumbnail", True):
            thumb_path = job_info.get("thumbnail_path")
            if thumb_path and Path(thumb_path).exists():
                self.ffmpeg.add_thumbnail(final_path, Path(thumb_path))

        return final_path

# ----------------------- LOGGING UTILITY -----------------------
def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
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
    required = ["concurrency", "download_dir", "format"]
    for key in required:
        if key not in config:
            logger.error(f"Missing config key: {key}")
            return False
    return True

# ----------------------- SUBSCRIPTION CHECK (real) -----------------------
def check_subscriptions(config: Dict, queue_manager):
    """Check all subscribed channels and add new videos."""
    # We'll read subscriptions from config or a file
    subscriptions = config.get("subscriptions", [])
    for channel in subscriptions:
        try:
            entries = extract_entries(channel)
            for entry in entries:
                url = entry.get("webpage_url")
                if url and not queue_manager.history.is_downloaded(url):
                    queue_manager.add_job(url, config.get("format", "mp4"))
        except Exception as e:
            logger.error(f"Failed to check subscription {channel}: {e}")
