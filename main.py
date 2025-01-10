import json
import time
import random
from playwright.sync_api import sync_playwright


class YouTubeStreamEngager:
    def __init__(self, accounts_file):
        with open(accounts_file, 'r') as f:
            self.accounts = json.load(f)
        self.current_account = 0

    def login_youtube(self, page, username, password):
        """Complete login process with better navigation handling"""
        try:
            # Clear cookies first
            page.context.clear_cookies()

            # Go to YouTube first
            page.goto('https://www.youtube.com')
            time.sleep(2)

            # Click the sign-in button on YouTube
            page.click('a[aria-label="Sign in"]')

            # Handle email
            page.wait_for_selector('input[type="email"]')
            self.type_humanlike(page, 'input[type="email"]', username)
            page.click('button:has-text("Next")')

            # Handle password
            page.wait_for_selector('input[type="password"]', state='visible')
            self.type_humanlike(page, 'input[type="password"]', password)
            page.click('button:has-text("Next")')

            # Wait for navigation back to YouTube
            page.wait_for_url('https://www.youtube.com/**')
            time.sleep(5)

            print("Initial login completed, proceeding...")

        except Exception as e:
            print(f"Login process error: {str(e)}")
            page.screenshot(path=f'login_error_{int(time.time())}.png')
            raise e

    def type_humanlike(self, page, selector, text):
        """Types text with random delays between characters"""
        for char in text:
            page.type(selector, char, delay=random.randint(100, 300))
            time.sleep(random.uniform(0.1, 0.3))

    def navigate_to_stream(self, page, stream_url):
        """Handle navigation to stream with verification"""
        try:
            print(f"Navigating to stream: {stream_url}")
            page.goto(stream_url, wait_until='networkidle')
            time.sleep(5)

            # Check if we're actually on the stream page
            current_url = page.url
            if 'watch?v=' not in current_url:
                raise Exception(f"Failed to reach stream. Current URL: {current_url}")

            return True

        except Exception as e:
            print(f"Navigation error: {str(e)}")
            return False

    def post_comment(self, stream_url, comment):
        """Posts a single comment to a YouTube stream"""
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-sandbox',
                    '--disable-web-security'
                ]
            )

            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation', 'notifications'],
                ignore_https_errors=True
            )

            page = context.new_page()
            account = self.accounts[self.current_account]

            try:
                # Perform login
                self.login_youtube(page, account['username'], account['password'])

                # Navigate to stream with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    if self.navigate_to_stream(page, stream_url):
                        break
                    if attempt < max_retries - 1:
                        print(f"Retry {attempt + 1} of {max_retries}...")
                        time.sleep(3)

                # Ensure we're on the stream page
                if 'watch?v=' not in page.url:
                    raise Exception("Failed to reach stream after retries")

                # Wait for video player
                page.wait_for_selector('video', timeout=10000)

                # Scroll to comments
                page.evaluate('window.scrollTo(0, document.querySelector("#comments").offsetTop)')
                time.sleep(2)

                # Look for comment box
                comment_box = page.wait_for_selector('#simplebox-placeholder')
                if not comment_box:
                    raise Exception("Comment box not found")

                comment_box.click()
                time.sleep(1)

                # Type comment
                comment_input = page.wait_for_selector('#contenteditable-textarea')
                self.type_humanlike(page, '#contenteditable-textarea', comment)
                time.sleep(random.uniform(1, 2))

                # Submit comment
                page.keyboard.press('Enter')
                time.sleep(3)

                print(f"Comment posted successfully as {account['username']}")

            except Exception as e:
                print(f"Error during process: {str(e)}")
                page.screenshot(path=f'error_{int(time.time())}.png')

            finally:
                browser.close()

            # Rotate account
            self.current_account = (self.current_account + 1) % len(self.accounts)

            # Random delay
            delay = random.randint(60, 180)
            print(f"Waiting {delay} seconds before next action...")
            time.sleep(delay)

    def post_comment_to_stream_chat(self, stream_url, comment):
        """Posts a single comment to a YouTube stream's live chat."""
        from playwright.sync_api import TimeoutError, expect

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-sandbox',
                    '--disable-web-security'
                ]
            )

            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation', 'notifications'],
                ignore_https_errors=True
            )

            page = context.new_page()
            account = self.accounts[self.current_account]

            try:
                # Perform login
                self.login_youtube(page, account['username'], account['password'])

                # Navigate to stream and wait for chat to load
                print(f"Navigating to stream: {stream_url}")
                page.goto(stream_url)

                # Wait for the main video player to load
                page.wait_for_selector('video', timeout=60000)
                page.wait_for_load_state('networkidle', timeout=60000)
                page.wait_for_timeout(5000)  # Extra wait for chat to initialize

                # First try to find chat frame
                chat_frame = page.frame_locator('iframe#chatframe')

                # If not found, try to expand chat
                if not chat_frame:
                    try:
                        expand_chat = page.get_by_role('button', name='Show chat').first
                        if expand_chat:
                            expand_chat.click()
                            page.wait_for_timeout(3000)
                            chat_frame = page.frame_locator('iframe#chatframe')
                    except Exception as e:
                        print(f"Note: Chat expansion failed: {str(e)}")

                if not chat_frame:
                    raise Exception("Could not locate chat iframe")

                # Wait for and find the exact chat input element
                exact_input_selector = 'div#input[contenteditable].style-scope.yt-live-chat-text-input-field-renderer'

                print("Waiting for chat input to be available...")
                chat_input = chat_frame.locator(exact_input_selector)
                chat_input.wait_for(state='visible', timeout=10000)

                if not chat_input.is_visible():
                    raise Exception("Chat input is not visible")

                # Click the input and wait for it to be ready
                chat_input.click()
                page.wait_for_timeout(1500)

                # Clear any existing text and type the comment
                chat_input.fill('')
                page.wait_for_timeout(1000)

                # Type comment with human-like delays
                for char in comment:
                    chat_input.type(char, delay=random.randint(50, 150))

                page.wait_for_timeout(1500)

                # Find and click the exact send button
                send_button_selector = '#send-button > yt-button-renderer > yt-button-shape > button'
                send_button = chat_frame.locator(send_button_selector).first

                if send_button.is_visible():
                    send_button.click()
                    print(f"Comment posted successfully as {account['username']}")
                else:
                    # Fallback to Enter key if button not visible
                    chat_input.press('Enter')
                    print(f"Comment posted using Enter key as {account['username']}")

            except TimeoutError as te:
                print(f"Timeout error: {str(te)}")
                page.screenshot(path=f'timeout_error_{int(time.time())}.png')
                raise

            except Exception as e:
                print(f"Error during process: {str(e)}")
                page.screenshot(path=f'error_{int(time.time())}.png')
                raise

            finally:
                try:
                    browser.close()
                except Exception:
                    pass

                # Rotate account
                self.current_account = (self.current_account + 1) % len(self.accounts)

                # Random delay between comments
                delay = random.randint(60, 180)
                print(f"Waiting {delay} seconds before next action...")
                time.sleep(delay)


def main():
    accounts_file = 'accounts.json'
    stream_url = input("Enter the YouTube stream URL: ")  # Get URL from user
    if not stream_url:
        stream_url = 'https://www.youtube.com/watch?v=ctyzvJLoid0'
    comments = [
        "Great stream! Really enjoying the content!",
        "Thanks for sharing your insights on this topic",
        "This is very informative, keep it up!"
    ]

    engager = YouTubeStreamEngager(accounts_file)

    for _ in range(3):
        comment = random.choice(comments)
        #engager.post_comment(stream_url, comment)
        engager.post_comment_to_stream_chat(stream_url, comment)


if __name__ == "__main__":
    main()