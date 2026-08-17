import yt_dlp
import time
import sys
import os

# ---------- CONFIG ----------
DELAY_BETWEEN_PLAYLIST_ITEMS = 2   # seconds; set to 0 to disable
# ----------------------------

def sanitize_filename(filename, max_length=255):
    """Remove invalid characters from filename"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # Trim to safe length
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext) - 1] + ext
    return filename

def download_single_video(url, is_mp3):
    """Download one video at best quality."""
    try:
        if is_mp3:
            format_spec = 'bestaudio/best'
            outtmpl = '%(title)s.%(ext)s'
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            # Force MP4 container with best video+audio
            format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            outtmpl = '%(title)s.%(ext)s'
            postprocessors = []

        ydl_opts = {
            'format': format_spec,
            'outtmpl': outtmpl,
            'noplaylist': True,
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,
            'postprocessors': postprocessors,
            'progress_hooks': [progress_hook],
            # FIX: Enable JavaScript runtime for YouTube
            'compat_options': ['--remote-components', 'ejs:npm'],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            return True
            
    except yt_dlp.utils.DownloadError as e:
        print(f"\n[ERROR] Download failed: {e}")
        return False
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return False

def progress_hook(d):
    """Show download progress"""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '').strip()
        speed = d.get('_speed_str', '').strip()
        if percent and speed:
            print(f"\rDownloading: {percent} at {speed}", end='')
    elif d['status'] == 'finished':
        print("\nDownload complete!")

def download_playlist_or_channel(url, is_mp3):
    """Extract entries and download each with a delay."""
    try:
        with yt_dlp.YoutubeDL({
            'quiet': True, 
            'extract_flat': False,
            'ignoreerrors': True,
            'no_warnings': True,
            # Also add JS runtime to the extractor
            'compat_options': ['--remote-components', 'ejs:npm'],
        }) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info is None:
                print("[ERROR] No info fetched. Check URL.")
                return False
            
            # Handle single video
            if 'entries' not in info:
                print(f"\nSingle video detected: {info.get('title', 'Unknown')}")
                return download_single_video(url, is_mp3)
            
            entries = info.get('entries', [])
            if not entries:
                print("[ERROR] Playlist or channel is empty.")
                return False
            
            total = len(entries)
            print(f"Found {total} items.")
            success_count = 0
            
            for idx, entry in enumerate(entries, 1):
                if entry is None:
                    print(f"\n[WARN] Item {idx} is unavailable, skipping...")
                    continue
                    
                video_url = entry.get('webpage_url') or entry.get('url')
                if not video_url:
                    print(f"\n[WARN] No URL for item {idx}, skipping...")
                    continue
                    
                print(f"\n=== Downloading {idx}/{total}: {entry.get('title', 'Unknown')} ===")
                if download_single_video(video_url, is_mp3):
                    success_count += 1
                else:
                    print(f"[WARN] Failed to download item {idx}")
                
                if idx < total and DELAY_BETWEEN_PLAYLIST_ITEMS > 0:
                    print(f"Waiting {DELAY_BETWEEN_PLAYLIST_ITEMS}s...")
                    time.sleep(DELAY_BETWEEN_PLAYLIST_ITEMS)
            
            print(f"\n=== SUMMARY: {success_count}/{total} items downloaded successfully ===")
            return success_count > 0
            
    except yt_dlp.utils.DownloadError as e:
        print(f"[ERROR] yt-dlp error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False

def validate_url(url):
    """Basic URL validation"""
    url = url.strip()
    if not url:
        return None
    if not (url.startswith('http://') or url.startswith('https://')):
        url = 'https://' + url
    return url

def check_runtime():
    """Check if Deno or Node is available"""
    import subprocess
    import shutil
    
    runtimes = ['deno', 'node', 'bun']
    found = []
    
    for runtime in runtimes:
        if shutil.which(runtime):
            try:
                result = subprocess.run([runtime, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=2)
                if result.returncode == 0:
                    version = result.stdout.strip().split('\n')[0]
                    found.append(f"{runtime} ({version})")
            except:
                pass
    
    if not found:
        print("\n⚠️ WARNING: No JavaScript runtime found!")
        print("YouTube downloads will likely fail with 403 errors.")
        print("\nInstall one of these:")
        print("  • Deno: https://deno.com/")
        print("  • Node: https://nodejs.org/")
        print("  • Bun: https://bun.sh/")
        print("\nThe script will continue, but may fail.\n")
        return False
    
    print(f"✅ Found JavaScript runtime(s): {', '.join(found)}")
    return True

def main():
    print("=== YouTube Downloader (yt-dlp) ===\n")
    
    # Check for JS runtime first
    print("Checking for required JavaScript runtime...")
    check_runtime()
    print()
    
    # Get URL with validation
    while True:
        url = input("Enter YouTube URL (video, playlist, or channel): ").strip()
        url = validate_url(url)
        if url:
            break
        print("[ERROR] Please enter a valid URL.")
    
    # Get format with validation and retry
    while True:
        format_type = input("Enter format (mp4 or mp3): ").strip().lower()
        if format_type in ('mp4', 'mp3'):
            break
        print("[ERROR] Invalid format. Please enter 'mp4' or 'mp3'.")
    
    is_mp3 = (format_type == 'mp3')
    
    # Confirm before downloading
    print(f"\nAbout to download: {url}")
    print(f"Format: {'MP3 (audio only)' if is_mp3 else 'MP4 (video+audio)'}")
    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm not in ('y', 'yes'):
        print("Cancelled.")
        return
    
    print("\nStarting download...\n")
    success = download_playlist_or_channel(url, is_mp3)
    
    if success:
        print("\n✅ All downloads completed successfully!")
    else:
        print("\n❌ Some downloads failed. Check errors above.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {e}")
        sys.exit(1)
