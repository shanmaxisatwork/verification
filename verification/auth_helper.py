import os
import sys
import time
from playwright.sync_api import sync_playwright

def generate_session(account_index):
    session_dir = "verification/sessions"
    os.makedirs(session_dir, exist_ok=True)
    session_path = os.path.join(session_dir, f"session_acc_{account_index}.json")

    print(f"\n--- [STEALTH MODE] SESSION GENERATOR FOR ACCOUNT #{account_index} ---")
    print(f"1. A STEALTH browser window will open.")
    print(f"2. Log in to your YouTube account.")
    print(f"3. Once you are logged in, return here.")
    print(f"4. Press ENTER in this terminal to save and close.")
    
    with sync_playwright() as p:
        # Launch using 'chrome' channel if available, which is less likely to be blocked
        # We also add arguments to hide the 'automation' flags
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        # Set a realistic user agent
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        
        context = browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1280, 'height': 720}
        )
        
        # Additional stealth: override the webdriver property
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page.goto("https://accounts.google.com/ServiceLogin?service=youtube")
        
        input("\n>>> Press ENTER here AFTER you have finished logging in... ")
        
        # Save the storage state
        context.storage_state(path=session_path)
        print(f"\n✅ SUCCESS! Session saved to: {session_path}")
        
        browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verification/auth_helper.py <account_index_1_to_5>")
        sys.exit(1)
        
    try:
        idx = int(sys.argv[1])
        generate_session(idx)
    except Exception as e:
        print(f"Error: {e}")
