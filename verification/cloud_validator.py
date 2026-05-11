import os
import json
import time
import cv2
import numpy as np
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "state" / "download_queue.json"
STATUS_FILE = BASE_DIR / "verification" / "verify_status.json"
WATERMARK_TEMPLATE = BASE_DIR / "watermark" / "watermark.png"
SESSIONS_DIR = BASE_DIR / "verification" / "sessions"

# Load Config for Telegram
CONFIG_PATH = BASE_DIR / "laptop_config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

TELEGRAM_BOT_TOKEN = CONFIG["telegram_bot_token"]
TELEGRAM_CHAT_ID = CONFIG["telegram_chat_id"]

def telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except:
        pass

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def verify_logo(screenshot_path):
    """Uses OpenCV template matching to find the logo in the top-right corner."""
    try:
        img_rgb = cv2.imread(screenshot_path)
        template = cv2.imread(str(WATERMARK_TEMPLATE))
        
        if img_rgb is None or template is None:
            return False, 0.0

        # Focus on the top-right quadrant to avoid false positives and speed up
        h, w = img_rgb.shape[:2]
        roi = img_rgb[0:h//2, w//2:w]
        
        # Scale template to match 8% width (as done in 3_add_watermark.py)
        target_w = int(w * 0.08)
        scale_factor = target_w / template.shape[1]
        target_h = int(template.shape[0] * scale_factor)
        template_resized = cv2.resize(template, (target_w, target_h))

        res = cv2.matchTemplate(roi, template_resized, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        return max_val > 0.7, max_val  # 0.7 is a safe threshold for semi-transparent logos
    except Exception as e:
        print(f"Error in CV: {e}")
        return False, 0.0

def run_verification(video_url, account_index):
    session_path = SESSIONS_DIR / f"session_acc_{account_index}.json"
    if not session_path.exists():
        print(f"Skipping Account {account_index}: Session file not found.")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use storage state for persistent login
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        
        try:
            print(f"Navigating to {video_url} with Account {account_index}...")
            page.goto(video_url, wait_until="networkidle")
            
            # 1. Find duration
            duration_sec = page.evaluate('''() => {
                const video = document.querySelector('video');
                return video ? video.duration : 0;
            }''')
            
            if duration_sec == 0:
                # Try waiting a bit more
                time.sleep(5)
                duration_sec = page.evaluate('document.querySelector("video").duration')

            print(f"Video duration: {duration_sec}s")
            
            # 2. Seek to 30s before end
            seek_time = max(0, duration_sec - 30)
            page.evaluate(f'document.querySelector("video").currentTime = {seek_time}')
            time.sleep(3) # Wait for seek to complete and frame to render
            
            # 3. Take screenshot
            os.makedirs("verification/temp", exist_ok=True)
            shot_path = f"verification/temp/shot_acc_{account_index}.png"
            page.screenshot(path=shot_path)
            
            # 4. Verify Logo
            success, score = verify_logo(shot_path)
            
            browser.close()
            return {"success": success, "score": score, "timestamp": datetime.now().isoformat()}
            
        except Exception as e:
            print(f"Playwright error: {e}")
            browser.close()
            return None

def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Cloud Watermark Validator")
    print(f"{'='*60}\n")

    queue = load_json(QUEUE_FILE, [])
    history = load_json(STATUS_FILE, {})

    uploaded_videos = [v for v in queue if v.get("status") == "uploaded"]
    
    if not uploaded_videos:
        print("No uploaded videos found in queue.")
        return

    for v in uploaded_videos:
        vid_id = v["yt_video_id"]
        link = v["yt_link"]
        title = v["title"]
        
        if vid_id not in history:
            history[vid_id] = {"title": title, "checks": {}}

        # Check for each of the 5 accounts
        for acc_idx in range(1, 6):
            acc_key = str(acc_idx)
            
            # Check if this account already verified this video
            if acc_key in history[vid_id]["checks"] and history[vid_id]["checks"][acc_key].get("success"):
                continue
            
            # Staggered logic: Only run if some time has passed since upload or previous check
            # For simplicity in GH Actions, we just run one pending check per video per run
            print(f"Verifying {title} with Account {acc_idx}...")
            result = run_verification(link, acc_idx)
            
            if result:
                history[vid_id]["checks"][acc_key] = result
                save_json(STATUS_FILE, history)
                
                status_emoji = "✅" if result["success"] else "❌"
                telegram(
                    f"{status_emoji} <b>Watermark Verified!</b>\n"
                    f"📹 {title[:50]}\n"
                    f"👤 Account: {acc_idx}\n"
                    f"🎯 Score: {result['score']:.2f}\n"
                    f"🔗 <a href='{link}'>Watch Video</a>"
                )
                
                if not result["success"]:
                    telegram(f"⚠️ <b>WARNING:</b> Logo not detected in top-right corner by Account {acc_idx}!")
                
                # Small pause between account switches
                time.sleep(10)
                break # Only one account check per video per execution to stay stealthy

if __name__ == "__main__":
    main()
