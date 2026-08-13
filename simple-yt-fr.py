import yt_dlp
import time

# ---------- CONFIG ----------
DELAY_BETWEEN_PLAYLIST_ITEMS = 2   # seconds; set to 0 to disable
# ----------------------------

def download_single_video(url, is_mp3):
    """Download one video at best quality."""
    if is_mp3:
        format_spec = 'bestaudio/best'
        outtmpl = '%(title)s.%(ext)s'
    else:
        format_spec = 'bestvideo+bestaudio/best'
        outtmpl = '%(title)s.%(ext)s'

    ydl_opts = {
        'format': format_spec,
        'outtmpl': outtmpl,
        'noplaylist': True,
        'quiet': False,           # show progress
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def download_playlist_or_channel(url, is_mp3):
    """Extract entries and download each with a delay."""
    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': False}) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            print("No info fetched.")
            return
        entries = info.get('entries', [])
        if not entries:
            # It's a single video, handle directly
            download_single_video(url, is_mp3)
            return

        print(f"Found {len(entries)} items.")
        for idx, entry in enumerate(entries, 1):
            if entry is None:
                continue
            video_url = entry.get('webpage_url') or entry.get('url')
            if video_url:
                print(f"\n--- Downloading {idx}/{len(entries)} ---")
                download_single_video(video_url, is_mp3)
                if idx < len(entries) and DELAY_BETWEEN_PLAYLIST_ITEMS > 0:
                    print(f"Waiting {DELAY_BETWEEN_PLAYLIST_ITEMS}s...")
                    time.sleep(DELAY_BETWEEN_PLAYLIST_ITEMS)

def main():
    url = input("Enter YouTube URL (video, playlist, or channel): ").strip()
    format_type = input("Enter format (mp4 or mp3): ").strip().lower()
    if format_type not in ('mp4', 'mp3'):
        print("Invalid format. Use 'mp4' or 'mp3'.")
        return

    is_mp3 = (format_type == 'mp3')
    download_playlist_or_channel(url, is_mp3)

if __name__ == "__main__":
    main()

# if you get any issues, tell me please. i will try to fix it. sorry for using AI but i have alot of preasure lately.
