#!/usr/bin/env python3
"""
test.py – Full system test for YT‑FR Pro.
Imports all modules, runs 6 automated tests, and checks device health.
"""

import sys
import os
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
import importlib.util

# ---------- 1. Import all modules (with graceful fallback) ----------
def import_modules():
    """Attempt to import all required modules from the project."""
    modules = {}
    try:
        import main as main_mod
        modules["main"] = main_mod
    except Exception as e:
        modules["main"] = f"Import failed: {e}"

    try:
        import core as core_mod
        modules["core"] = core_mod
    except Exception as e:
        modules["core"] = f"Import failed: {e}"

    try:
        import utils as utils_mod
        modules["utils"] = utils_mod
    except Exception as e:
        modules["utils"] = f"Import failed: {e}"

    return modules

# ---------- 2. Device capability checks (9 functions) ----------
def check_python_version():
    return sys.version_info >= (3, 9)

def check_cpu_cores():
    import multiprocessing
    return multiprocessing.cpu_count()

def check_ram_total():
    try:
        import psutil
        return psutil.virtual_memory().total / (1024**3)  # GB
    except:
        return 0

def check_ram_free():
    try:
        import psutil
        return psutil.virtual_memory().available / (1024**3)
    except:
        return 0

def check_disk_free(path="."):
    try:
        import psutil
        return psutil.disk_usage(path).free / (1024**3)
    except:
        return 0

def check_gpu_info():
    try:
        import utils
        info = utils.SystemMonitor.get_gpu_info()
        return info
    except:
        return {"name": "N/A", "memory_used": 0, "memory_total": 0}

def check_ffmpeg():
    return shutil.which("ffmpeg") is not None

def check_network_connectivity():
    try:
        import requests
        requests.get("https://httpbin.org/status/200", timeout=3)
        return True
    except:
        return False

def check_download_speed():
    try:
        import requests
        # Download a small file to estimate speed
        start = time.time()
        r = requests.get("https://httpbin.org/bytes/102400", timeout=5)
        duration = time.time() - start
        speed = len(r.content) / duration / 1024  # KB/s
        return speed
    except:
        return 0

# ---------- 3. Test functions (6 tests) ----------
def test_config_loading():
    """Test that config.yaml can be loaded or created."""
    try:
        from main import load_config
        config = load_config("config.yaml")
        if config and "concurrency" in config:
            return "PASS", config
        else:
            return "FAIL", "Config missing keys"
    except Exception as e:
        return "FAIL", str(e)

def test_proxy_manager():
    """Test proxy manager with mock proxies."""
    try:
        from core import ProxyManager
        pm = ProxyManager({"proxy": ["socks5://127.0.0.1:1080", "http://127.0.0.1:3128"]})
        p1 = pm.get_next_proxy()
        p2 = pm.get_next_proxy()
        pm.rotate()
        p3 = pm.get_next_proxy()
        if p1 != p2 and p1 != p3 and p2 != p3:
            return "PASS", "Rotation works"
        else:
            return "FAIL", "Proxy rotation not effective"
    except Exception as e:
        return "FAIL", str(e)

def test_ffmpeg_processor():
    """Test FFmpegProcessor with a dummy file (if FFmpeg installed)."""
    if not check_ffmpeg():
        return "SKIP", "FFmpeg not installed, skipping"
    try:
        from utils import FFmpegProcessor
        proc = FFmpegProcessor()
        # Create a dummy audio file (silence)
        temp_file = Path(tempfile.mktemp(suffix=".wav"))
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", "-q:a", "9", "-acodec", "pcm_s16le", str(temp_file)], check=True, capture_output=True)
        out_file = temp_file.with_suffix(".mp3")
        proc.convert(temp_file, out_file, "mp3")
        result = out_file.exists()
        temp_file.unlink(missing_ok=True)
        out_file.unlink(missing_ok=True)
        if result:
            return "PASS", "Converted wav to mp3 successfully"
        else:
            return "FAIL", "Conversion failed"
    except Exception as e:
        return "FAIL", str(e)

def test_queue_manager():
    """Test QueueManager with multiple jobs."""
    try:
        from core import QueueManager
        qm = QueueManager()
        qm.add_job("https://youtu.be/123", "mp4")
        qm.add_job("https://youtu.be/456", "mp3")
        job1 = qm.get_job()
        job2 = qm.get_job()
        if job1 and job2 and job1.url != job2.url:
            qm.job_done(job1)
            qm.job_done(job2)
            return "PASS", "Queue add/retrieve works"
        else:
            return "FAIL", "Queue items not retrieved correctly"
    except Exception as e:
        return "FAIL", str(e)

def test_resource_monitor():
    """Test SystemMonitor functions."""
    try:
        from utils import SystemMonitor
        cpu = SystemMonitor.get_cpu_percent()
        mem = SystemMonitor.get_memory_usage()
        disk = SystemMonitor.get_disk_usage(".")
        gpu = SystemMonitor.get_gpu_info()
        if isinstance(cpu, (int, float)) and "used" in mem and "total" in mem:
            return "PASS", f"CPU: {cpu}%, RAM: {mem['used']:.1f}GB/{mem['total']:.1f}GB, GPU: {gpu.get('name','N/A')}"
        else:
            return "FAIL", "Monitor returned unexpected data"
    except Exception as e:
        return "FAIL", str(e)

def test_download_manager_init():
    """Test DownloadManager initialisation with config."""
    try:
        from core import DownloadManager
        from main import load_config
        config = load_config("config.yaml")
        dm = DownloadManager(config)
        if dm.download_dir and dm.concurrency > 0:
            return "PASS", f"Manager initialised with concurrency {dm.concurrency}"
        else:
            return "FAIL", "Manager init incomplete"
    except Exception as e:
        return "FAIL", str(e)

# ---------- 4. Main runner ----------
def run_all_tests():
    print("=== YT‑FR Pro System Test ===")
    print("\n--- Module Imports ---")
    modules = import_modules()
    for name, status in modules.items():
        if "failed" in str(status).lower():
            print(f"  ❌ {name}: {status}")
        else:
            print(f"  ✅ {name} imported")

    print("\n--- Device Capabilities ---")
    print(f"  Python >=3.9: {'✅' if check_python_version() else '❌'}")
    cores = check_cpu_cores()
    print(f"  CPU cores: {cores}")
    ram_total = check_ram_total()
    ram_free = check_ram_free()
    print(f"  RAM: total {ram_total:.1f} GB, free {ram_free:.1f} GB")
    disk_free = check_disk_free()
    print(f"  Disk free: {disk_free:.1f} GB")
    gpu = check_gpu_info()
    print(f"  GPU: {gpu.get('name', 'N/A')} (Memory: {gpu.get('memory_used',0):.1f}/{gpu.get('memory_total',0):.1f} GB)")
    print(f"  FFmpeg installed: {'✅' if check_ffmpeg() else '❌'}")
    print(f"  Network reachable: {'✅' if check_network_connectivity() else '❌'}")
    speed = check_download_speed()
    print(f"  Download speed: {speed:.0f} KB/s")

    print("\n--- Running 6 Tests ---")
    test_results = []
    for name, func in [
        ("Config Loading", test_config_loading),
        ("Proxy Manager", test_proxy_manager),
        ("FFmpeg Processor", test_ffmpeg_processor),
        ("Queue Manager", test_queue_manager),
        ("Resource Monitor", test_resource_monitor),
        ("Download Manager Init", test_download_manager_init),
    ]:
        status, msg = func()
        if status == "PASS":
            symbol = "✅"
        elif status == "SKIP":
            symbol = "⏭️"
        else:
            symbol = "❌"
        test_results.append((name, status, msg))
        print(f"  {symbol} {name}: {msg}")

    # Summary
    passed = sum(1 for _, s, _ in test_results if s == "PASS")
    skipped = sum(1 for _, s, _ in test_results if s == "SKIP")
    failed = sum(1 for _, s, _ in test_results if s == "FAIL")
    print("\n--- Summary ---")
    print(f"✅ Passed: {passed}")
    print(f"⏭️ Skipped: {skipped}")
    print(f"❌ Failed: {failed}")
    if failed == 0:
        print("\n🎉 All tests passed! Your device is ready for YT‑FR Pro.")
    else:
        print("\n⚠️ Some tests failed. Check error messages and ensure dependencies are correct.")
        print("   Run 'python auto-setup.py' to fix common issues.")

if __name__ == "__main__":
    run_all_tests()