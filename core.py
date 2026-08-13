"""
Core modules: DownloadManager, QueueManager, ProxyManager, VPNManager, Scheduler, API stub.
"""

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
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import schedule

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

# ----------------------- PROXY MANAGER -----------------------
class ProxyManager:
    def __init__(self, config: Dict[str, Any]):
        self.proxies = config.get("proxy", [])
        if isinstance(self.proxies, str):
            self.proxies = [self.proxies]
        self.current_index = 0
        self.lock = threading.Lock()

    def get_next_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        with self.lock:
            proxy = self.proxies[self.current_index % len(self.proxies)]
            self.current_index += 1
            return proxy

    def rotate(self):
        with self.lock:
            self.current_index = (self.current_index + 1) % len(self.proxies) if self.proxies else 0

    def test_proxy(self, proxy: str) -> bool:
        """Test proxy connectivity."""
        try:
            proxies = {"http": proxy, "https": proxy}
            r = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=5)
            return r.status_code == 200
        except:
            return False

# ----------------------- VPN MANAGER (stub) -----------------------
class VPNManager:
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("vpn", {}).get("enabled", False)
        self.command = config.get("vpn", {}).get("command", "openvpn")
        self.config_file = config.get("vpn", {}).get("config", "")
        self.process = None

    def connect(self) -> bool:
        if not self.enabled:
            return True
        logger.info(f"Connecting VPN with {self.command} {self.config_file}")
        # Actual implementation would start openvpn/wireguard process
        # For demo, we simulate
        try:
            # self.process = subprocess.Popen([self.command, "--config", self.config_file], ...)
            logger.info("VPN connected (simulated).")
            return True
        except Exception as e:
            logger.error(f"VPN connection failed: {e}")
            return False

    def disconnect(self):
        if self.process:
            self.process.terminate()
            logger.info("VPN disconnected.")

    def killswitch(self):
        """Stop all downloads if VPN disconnects."""
        logger.warning("Killswitch triggered: stopping downloads.")
        # Implementation would signal DownloadManager to pause

# ----------------------- DOWNLOAD JOB -----------------------
class DownloadJob:
    def __init__(self, url: str, format: str, options: Dict[str, Any]):
        self.url = url
        self.format = format
        self.options = options
        self.status = "pending"
        self.result = None
        self.error = None
        self.progress = 0

    def __str__(self):
        return f"Job(url={self.url}, format={self.format})"

# ----------------------- QUEUE MANAGER -----------------------
class QueueManager:
    def __init__(self):
        self.jobs = queue.Queue()
        self.active_jobs = {}
        self.lock = threading.Lock()
        self.history = HistoryDB()

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

# ----------------------- DOWNLOAD MANAGER -----------------------
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
        self.executor = ThreadPoolExecutor(max_workers=self.concurrency)
        self.history = HistoryDB()
        self.format_map = {
            "mp4": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "mkv": "bestvideo[ext=mkv]+bestaudio/best[ext=mkv]",
            "webm": "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]",
            "mp3": "bestaudio/bestaudio"
        }

    def _get_ydl_opts(self, job: DownloadJob):
        """Generate yt-dlp options for a job."""
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
        }
        # Proxy
        proxy = job.options.get("proxy") or self.proxy_manager.get_next_proxy()
        if proxy:
            opts['proxy'] = proxy
        # Headers
        opts['headers'] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        # VPN killswitch – if VPN enabled, we add a check in hook
        return opts

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            if 'total_bytes' in d:
                percent = d['downloaded_bytes'] / d['total_bytes'] * 100
                logger.debug(f"Progress: {d['filename']} {percent:.1f}%")
        elif d['status'] == 'finished':
            logger.info(f"Download finished: {d['filename']}")

    def _download_single(self, job: DownloadJob) -> Dict[str, Any]:
        """Execute one download with retries and proxy rotation."""
        url = job.url
        attempt = 0
        last_error = None
        while attempt < self.retry_attempts:
            attempt += 1
            try:
                opts = self._get_ydl_opts(job)
                # Optionally handle VPN killswitch: pause if VPN down
                if self.vpn_manager.enabled and not self.vpn_manager.connected:
                    # Wait for reconnection
                    logger.warning("VPN disconnected, waiting...")
                    time.sleep(10)
                    continue

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        raise ValueError("No info extracted")
                    # Save result
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
                # Rotate proxy
                self.proxy_manager.rotate()
                # Exponential backoff
                sleep_time = self.backoff ** attempt
                time.sleep(sleep_time)
                continue
        job.status = "failed"
        job.error = last_error
        raise last_error

    def process_queue(self, queue_manager: QueueManager):
        """Continuously process jobs from queue with concurrency."""
        futures = []
        while self.running:
            # Submit new jobs if concurrency allows
            while len(futures) < self.concurrency:
                job = queue_manager.get_job()
                if job is None:
                    break
                future = self.executor.submit(self._download_single, job)
                future.job = job
                futures.append(future)

            # Check completed futures
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

            # If no jobs and no futures, break
            if queue_manager.jobs.empty() and not futures:
                break

            # Resource monitor – adjust concurrency dynamically
            if self.monitor:
                mem_usage = self.monitor.get_memory_usage()
                # If memory > 8GB used, reduce concurrency
                if mem_usage > 8.0:
                    new_concurrency = max(1, self.concurrency - 1)
                    if new_concurrency != self.concurrency:
                        logger.info(f"High memory usage ({mem_usage:.1f} GB), reducing concurrency to {new_concurrency}")
                        self.concurrency = new_concurrency
                        # Note: we don't shrink executor, but future submissions will respect new limit
                        # We'll just not submit more than self.concurrency
                # Also check GPU if needed for encoding

            time.sleep(1)

        self.executor.shutdown(wait=True)
        logger.info("Queue processing complete.")

    def shutdown(self):
        self.running = False
        self.executor.shutdown(wait=False)
        self.vpn_manager.disconnect()

# ----------------------- SCHEDULER (stub) -----------------------
class Scheduler:
    def __init__(self, config: Dict[str, Any], download_manager: DownloadManager):
        self.enabled = config.get("scheduler", {}).get("enabled", False)
        self.cron = config.get("scheduler", {}).get("cron", "0 0 * * *")
        self.dm = download_manager

    def start(self):
        if not self.enabled:
            return
        import schedule
        schedule.every().day.at("00:00").do(self.dm.check_subscriptions)  # stub
        while True:
            schedule.run_pending()
            time.sleep(60)

# ----------------------- API SERVER (stub) -----------------------
def start_api(config: Dict[str, Any], download_manager: DownloadManager):
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify({"status": "running", "active_jobs": len(download_manager.executor._threads)})

    @app.route("/submit", methods=["POST"])
    def submit():
        data = request.json
        url = data.get("url")
        if not url:
            return jsonify({"error": "No url"}), 400
        # Add to queue
        # We need a global queue manager reference; for simplicity, we assume it's passed
        return jsonify({"message": "Added"}), 202

    port = config.get("api", {}).get("port", 5000)
    app.run(host="0.0.0.0", port=port, debug=False)