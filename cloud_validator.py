import os
import json
import time
import cv2
import numpy as np
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from pathlib import Path

# Standalone Paths
BASE_DIR = Path(__file__).parent
QUEUE_FILE = BASE_DIR / "verify_queue.json"
STATUS_FILE = BASE_DIR / "verify_status.json"
WATERMARK_TEMPLATE = BASE_DIR / "watermark.png"
SESSIONS_DIR = BASE_DIR / "sessions"
CONFIG_FILE = BASE_DIR / "config.json"

# Load Config
if not CONFIG_FILE.exists():
    print("ERROR: config.json not found!")
    exit(1)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
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
    try:
        img_rgb = cv2.imread(screenshot_path)
        template = cv2.imread(str(WATERMARK_TEMPLATE))
        if img_rgb is None or template is None: return False, 0.0
        h, w = img_rgb.shape[:2]
        roi = img_rgb[0:h//2, w//2:w]
        target_w = int(w * 0.08)
        scale_factor = target_w / template.shape[1]
        target_h = int(template.shape[0] * scale_factor)
        template_resized = cv2.resize(template, (target_w, target_h))
        res = cv2.matchTemplate(roi, template_resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return max_val > 0.7, max_val
    except: return False, 0.0

def run_verification(video_url, account_index):
    session_path = SESSIONS_DIR / f"session_acc_{account_index}.json"
    if not session_path.exists(): return None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()
        try:
            page.goto(video_url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
            duration_sec = page.evaluate('document.querySelector("video") ? document.querySelector("video").duration : 0')
            if not duration_sec: return None
            page.evaluate(f'document.querySelector("video").currentTime = {max(0, duration_sec - 30)}')
            time.sleep(4)
            shot_path = f"shot_temp.png"
            page.screenshot(path=shot_path)
            success, score = verify_logo(shot_path)
            browser.close()
            return {"success": success, "score": score, "timestamp": datetime.now().isoformat()}
        except:
            browser.close()
            return None

def main():
    queue = load_json(QUEUE_FILE, [])
    history = load_json(STATUS_FILE, {})
    for v in queue:
        vid_id = v.get("yt_video_id")
        link = v.get("yt_link")
        title = v.get("title", "Unknown Video")
        if not vid_id or not link: continue
        if vid_id not in history: history[vid_id] = {"title": title, "checks": {}}
        for acc_idx in range(1, 6):
            acc_key = str(acc_idx)
            if acc_key in history[vid_id]["checks"] and history[vid_id]["checks"][acc_key].get("success"):
                continue
            print(f"Checking {title} with Acc {acc_idx}...")
            result = run_verification(link, acc_idx)
            if result:
                history[vid_id]["checks"][acc_key] = result
                save_json(STATUS_FILE, history)
                status = "✅" if result["success"] else "❌"
                telegram(f"{status} <b>Watermark Check</b>\n📹 {title[:50]}\n👤 Acc: {acc_idx}\n🎯 Score: {result['score']:.2f}")
                break
if __name__ == "__main__":
    main()
