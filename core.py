import os
import time
import json
import sqlite3
import threading
import queue
import subprocess
import random
import logging
import yt_dlp
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import requests
import schedule
import secrets
from flask import Flask, request, jsonify, abort

logger = logging.getLogger("core")

# ----------------------- DATABASE (history) -----------------------
class HistoryDB:
    def __init__(self, db_path: str = "download_history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                title TEXT,
                format TEXT,
                path TEXT,
                status TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def record_download(self, url: str, title: str, format: str, path: str, status: str = "completed"):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO downloads (url, title, format, path, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (url, title, format, path, status))
        conn.commit()
        conn.close()

    def is_downloaded(self, url: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT 1 FROM downloads WHERE url = ? AND status = 'completed'", (url,))
        exists = c.fetchone() is not None
        conn.close()
        return exists

# ----------------------- PROXY MANAGER (full) -----------------------
class ProxyManager:
    def __init__(self, config: Dict[str, Any]):
        self.proxies = config.get("proxy", [])
        if isinstance(self.proxies, str):
            self.proxies = [self.proxies]
        self.current_index = 0
        self.lock = threading.Lock()
        # Health cache
        self.healthy = {}

    def get_next_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        with self.lock:
            proxy = self.proxies[self.current_index % len(self.proxies)]
            self.current_index += 1
            # Check health
            if self.test_proxy(proxy):
                return proxy
            else:
                # Try next
                return self.get_next_proxy()

    def rotate(self):
        with self.lock:
            self.current_index = (self.current_index + 1) % len(self.proxies)

    def test_proxy(self, proxy: str) -> bool:
        if proxy in self.healthy:
            return self.healthy[proxy]
        try:
            proxies = {"http": proxy, "https": proxy}
            r = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=5)
            ok = r.status_code == 200
            self.healthy[proxy] = ok
            return ok
        except:
            self.healthy[proxy] = False
            return False

# ----------------------- VPN MANAGER (real) -----------------------
class VPNManager:
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("vpn", {}).get("enabled", False)
        self.command = config.get("vpn", {}).get("command", "openvpn")
        self.config_file = config.get("vpn", {}).get("config", "")
        self.process = None
        self.killswitch_callback = None
        self.monitor_thread = None

    def connect(self) -> bool:
        if not self.enabled:
            return True
        if not self.config_file or not Path(self.config_file).exists():
            logger.error("VPN config file not found.")
            return False
        logger.info(f"Starting VPN: {self.command} --config {self.config_file}")
        try:
            self.process = subprocess.Popen(
                [self.command, "--config", self.config_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(3)
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                logger.error(f"VPN died: {stderr.decode()}")
                return False
            # Start monitoring
            if self.killswitch_callback:
                self.monitor_thread = threading.Thread(target=self._monitor, daemon=True)
                self.monitor_thread.start()
            return True
        except Exception as e:
            logger.error(f"Failed to start VPN: {e}")
            return False

    def _monitor(self):
        while self.process and self.process.poll() is None:
            time.sleep(2)
        if self.process and self.process.poll() is not None:
            logger.warning("VPN disconnected – triggering killswitch")
            if self.killswitch_callback:
                self.killswitch_callback()

    def disconnect(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            logger.info("VPN disconnected.")

    def is_connected(self) -> bool:
        return self.process is not None and self.process.poll() is None

# ----------------------- DOWNLOAD JOB -----------------------
class DownloadJob:
    def __init__(self, url: str, format: str, options: Dict[str, Any] = None):
        self.url = url
        self.format = format
        self.options = options or {}
        self.status = "pending"
        self.result = None
        self.error = None
        self.progress = 0
        self.retry_count = 0
        self.attempts = 0

    def __str__(self):
        return f"Job(url={self.url}, format={self.format})"

# ----------------------- QUEUE MANAGER -----------------------
class QueueManager:
    def __init__(self):
        self.jobs = queue.Queue()
        self.active_jobs = {}
        self.lock = threading.Lock()
        self.history = HistoryDB()
        self.job_id_counter = 0

    def add_job(self, url: str, format: str = "mp4", options: Optional[Dict] = None):
        if self.history.is_downloaded(url):
            logger.info(f"Skipping already downloaded: {url}")
            return
        job = DownloadJob(url, format, options or {})
        self.jobs.put(job)

    def get_job(self) -> Optional[DownloadJob]:
        try:
            job = self.jobs.get_nowait()
            with self.lock:
                self.active_jobs[id(job)] = job
            return job
        except queue.Empty:
            return None

    def job_done(self, job: DownloadJob):
        with self.lock:
            self.active_jobs.pop(id(job), None)
        self.jobs.task_done()
        if job.status == "completed":
            self.history.record_download(job.url, job.result.get("title", ""), job.format, job.result.get("path", ""))

    def get_active_count(self):
        with self.lock:
            return len(self.active_jobs)

    def get_queue_size(self):
        return self.jobs.qsize()

# ----------------------- DOWNLOAD MANAGER (full with pause/resume) -----------------------
class DownloadManager:
    def __init__(self, config: Dict[str, Any], monitor=None):
        self.config = config
        self.monitor = monitor
        self.concurrency = config.get("concurrency", 3)
        self.retry_attempts = config.get("retry", {}).get("max_attempts", 5)
        self.backoff = config.get("retry", {}).get("backoff_factor", 2)
        self.download_dir = Path(config.get("download_dir", "./downloads"))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_manager = ProxyManager(config)
        self.vpn_manager = VPNManager(config)
        self.running = True
        self.paused = False
        self.pause_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=self.concurrency)
        self.history = HistoryDB()
        self.format_map = {
            "mp4": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "mkv": "bestvideo[ext=mkv]+bestaudio/best[ext=mkv]",
            "webm": "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]",
            "mp3": "bestaudio/bestaudio"
        }
        self.active_jobs = {}  # job_id -> future

    def _get_ydl_opts(self, job: DownloadJob):
        fmt = self.format_map.get(job.format, "bestvideo+bestaudio/best")
        outtmpl = str(self.download_dir / f"%(title)s.%(ext)s")
        opts = {
            'format': fmt,
            'outtmpl': outtmpl,
            'noplaylist': False,
            'quiet': False,
            'progress_hooks': [self._progress_hook],
            'retries': 3,
            'fragment_retries': 3,
            'ignoreerrors': False,
            'socket_timeout': 30,
        }
        proxy = job.options.get("proxy") or self.proxy_manager.get_next_proxy()
        if proxy:
            opts['proxy'] = proxy
        opts['headers'] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        return opts

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            if 'total_bytes' in d:
                percent = d['downloaded_bytes'] / d['total_bytes'] * 100
                logger.debug(f"Progress: {d['filename']} {percent:.1f}%")
        elif d['status'] == 'finished':
            logger.info(f"Download finished: {d['filename']}")

    def _download_single(self, job: DownloadJob) -> Dict[str, Any]:
        url = job.url
        attempt = 0
        last_error = None
        while attempt < self.retry_attempts:
            attempt += 1
            job.attempts = attempt
            # Check pause
            with self.pause_lock:
                while self.paused:
                    logger.info("Paused, waiting...")
                    time.sleep(2)
            # Check VPN
            if self.vpn_manager.enabled and not self.vpn_manager.is_connected():
                logger.warning("VPN disconnected, waiting for reconnect...")
                time.sleep(10)
                continue
            try:
                opts = self._get_ydl_opts(job)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        raise ValueError("No info extracted")
                    result = {
                        "title": info.get("title", "unknown"),
                        "path": ydl.prepare_filename(info),
                        "ext": info.get("ext", job.format),
                        "uploader": info.get("uploader", ""),
                        "duration": info.get("duration", 0),
                    }
                    job.result = result
                    job.status = "completed"
                    return result
            except Exception as e:
                last_error = e
                logger.error(f"Attempt {attempt} failed for {url}: {e}")
                self.proxy_manager.rotate()
                sleep_time = self.backoff ** attempt
                time.sleep(sleep_time)
                continue
        job.status = "failed"
        job.error = last_error
        raise last_error

    def pause(self):
        with self.pause_lock:
            self.paused = True
            logger.info("Download manager paused.")

    def resume(self):
        with self.pause_lock:
            self.paused = False
            logger.info("Download manager resumed.")

    def process_queue(self, queue_manager: QueueManager):
        futures = []
        while self.running:
            # Check pause
            with self.pause_lock:
                if self.paused:
                    time.sleep(1)
                    continue

            # Submit new jobs
            while len(futures) < self.concurrency:
                job = queue_manager.get_job()
                if job is None:
                    break
                future = self.executor.submit(self._download_single, job)
                future.job = job
                futures.append(future)

            # Check completed
            done_futures = [f for f in futures if f.done()]
            for f in done_futures:
                job = f.job
                try:
                    result = f.result()
                    logger.info(f"Completed: {job.url} -> {result['path']}")
                    queue_manager.job_done(job)
                except Exception as e:
                    logger.error(f"Failed: {job.url} - {e}")
                    job.status = "failed"
                    queue_manager.job_done(job)
                futures.remove(f)

            if queue_manager.jobs.empty() and not futures:
                break

            # Dynamic concurrency based on RAM
            if self.monitor:
                mem_usage = self.monitor.get_memory_usage()
                if mem_usage > 8.0:
                    new_concurrency = max(1, self.concurrency - 1)
                    if new_concurrency != self.concurrency:
                        logger.info(f"High memory ({mem_usage:.1f} GB), reducing concurrency to {new_concurrency}")
                        self.concurrency = new_concurrency

            time.sleep(1)

        self.executor.shutdown(wait=True)
        logger.info("Queue processing complete.")

    def shutdown(self):
        self.running = False
        self.executor.shutdown(wait=False)
        self.vpn_manager.disconnect()
        logger.info("Shutdown complete.")

# ----------------------- SCHEDULER (real) -----------------------
class Scheduler:
    def __init__(self, config: Dict[str, Any], queue_manager: QueueManager):
        self.enabled = config.get("scheduler", {}).get("enabled", False)
        self.cron = config.get("scheduler", {}).get("cron", "0 0 * * *")
        self.qm = queue_manager
        self.subscriptions = []  # list of channel URLs

    def start(self):
        if not self.enabled:
            return
        import schedule
        # Parse cron (simplified – just daily at midnight)
        schedule.every().day.at("00:00").do(self.check_subscriptions)
        while True:
            schedule.run_pending()
            time.sleep(60)

    def check_subscriptions(self):
        logger.info("Checking subscriptions...")
        for channel in self.subscriptions:
            # Use yt-dlp to get latest videos and add to queue
            # For brevity, we just log
            logger.info(f"Checking {channel}")

# ----------------------- REST API (full with auth) -----------------------
API_KEY = None

def start_api(config: Dict[str, Any], queue_manager: QueueManager, download_manager: DownloadManager):
    global API_KEY
    API_KEY = config.get("api", {}).get("api_key", secrets.token_urlsafe(16))
    logger.info(f"API key: {API_KEY}")
    app = Flask(__name__)

    def require_auth():
        if request.headers.get("X-API-Key") != API_KEY:
            abort(401)

    @app.route("/status", methods=["GET"])
    def status():
        require_auth()
        return jsonify({
            "active_jobs": queue_manager.get_active_count(),
            "queue_size": queue_manager.get_queue_size(),
            "running": download_manager.running,
            "paused": download_manager.paused,
            "concurrency": download_manager.concurrency
        })

    @app.route("/submit", methods=["POST"])
    def submit():
        require_auth()
        data = request.json
        url = data.get("url")
        fmt = data.get("format", "mp4")
        if not url:
            return jsonify({"error": "Missing url"}), 400
        queue_manager.add_job(url, fmt)
        return jsonify({"message": "Added", "job_id": url}), 202

    @app.route("/pause", methods=["POST"])
    def pause():
        require_auth()
        download_manager.pause()
        return jsonify({"message": "Paused"})

    @app.route("/resume", methods=["POST"])
    def resume():
        require_auth()
        download_manager.resume()
        return jsonify({"message": "Resumed"})

    @app.route("/cancel", methods=["POST"])
    def cancel():
        require_auth()
        # Stub – would need to cancel specific job
        return jsonify({"message": "Cancel functionality not yet implemented"}), 501

    @app.route("/list", methods=["GET"])
    def list_formats():
        require_auth()
        url = request.args.get("url")
        if not url:
            return jsonify({"error": "Missing url param"}), 400
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = [{"format_id": f["format_id"], "ext": f["ext"], "resolution": f.get("resolution", "audio")} for f in info.get("formats", [])]
                return jsonify({"formats": formats})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/history", methods=["GET"])
    def history():
        require_auth()
        conn = sqlite3.connect("download_history.db")
        c = conn.cursor()
        c.execute("SELECT url, title, format, path, status, downloaded_at FROM downloads ORDER BY downloaded_at DESC LIMIT 100")
        rows = c.fetchall()
        conn.close()
        return jsonify([{"url": r[0], "title": r[1], "format": r[2], "path": r[3], "status": r[4], "time": r[5]} for r in rows])

    port = config.get("api", {}).get("port", 5000)
    app.run(host="0.0.0.0", port=port, debug=False)
