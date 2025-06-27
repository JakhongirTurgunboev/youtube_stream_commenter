import json
import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Thread
from playwright.sync_api import sync_playwright
from typing import List, Dict
from queue import Queue


class BrowserWorker:
    def __init__(self, account: Dict):
        self.account = account
        self.username = account['username']
        self.password = account['password']
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
        self.comment_queue = Queue()
        self.stop_flag = False
        self.setup_logging()

    def setup_logging(self):
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('youtube_comments.log'),
                    logging.StreamHandler()
                ]
            )

    def initialize_browser(self):
        """Initialize browser session"""
        try:
            playwright = sync_playwright().start()
            self.browser = playwright.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-sandbox',
                    '--disable-web-security'
                ]
            )

            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation', 'notifications'],
                ignore_https_errors=True
            )

            self.page = self.context.new_page()
            return True
        except Exception as e:
            logging.error(f"Browser initialization error for {self.username}: {str(e)}")
            return False

    def type_humanlike(self, selector: str, text: str):
        """Type with human-like delays"""
        for char in text:
            self.page.type(selector, char, delay=random.randint(100, 300))
            time.sleep(random.uniform(0.1, 0.3))

    def login(self) -> bool:
        """Perform login once"""
        if self.is_logged_in:
            return True

        try:
            logging.info(f"Logging in {self.username}")
            self.page.goto('https://www.youtube.com')
            time.sleep(random.uniform(2, 4))

            self.page.click('a[aria-label="Sign in"]')
            self.page.wait_for_selector('input[type="email"]')
            self.type_humanlike('input[type="email"]', self.username)
            self.page.click('button:has-text("Next")')

            self.page.wait_for_selector('input[type="password"]', state='visible')
            self.type_humanlike('input[type="password"]', self.password)
            self.page.click('button:has-text("Next")')

            self.page.wait_for_url('https://www.youtube.com/**')
            time.sleep(random.uniform(3, 5))

            self.is_logged_in = True
            logging.info(f"Login successful for {self.username}")
            return True

        except Exception as e:
            logging.error(f"Login error for {self.username}: {str(e)}")
            self.page.screenshot(path=f'error_screenshot/login_error_{self.username}_{int(time.time())}.png')
            return False

    def post_comment(self, video_url: str, comment: str) -> bool:
        """Post a single comment on a video"""
        try:
            if not self.is_logged_in and not self.login():
                return False

            logging.info(f"Navigating to video as {self.username}")
            self.page.goto(video_url)
            self.page.wait_for_selector('video', timeout=60000)
            self.page.wait_for_load_state('networkidle', timeout=60000)

            # Scroll to comments section
            self.page.evaluate('''() => {
                window.scrollBy(0, window.innerHeight);
            }''')
            time.sleep(random.uniform(2, 4))

            # Wait for and click on comment box
            comment_box = self.page.locator('#simplebox-placeholder')
            comment_box.wait_for(state='visible', timeout=10000)
            comment_box.click()
            time.sleep(random.uniform(1, 2))

            # Type the comment
            comment_input = self.page.locator('#contenteditable-root')
            comment_input.wait_for(state='visible', timeout=10000)

            for char in comment:
                comment_input.type(char, delay=random.randint(50, 200))
            time.sleep(random.uniform(1, 2))

            # Click submit button
            submit_button = self.page.locator('#submit-button')
            submit_button.wait_for(state='visible', timeout=10000)
            submit_button.click()

            # Wait for comment to be posted
            time.sleep(random.uniform(2, 4))

            logging.info(f"Comment posted successfully as {self.username}")
            return True

        except Exception as e:
            logging.error(f"Error posting comment as {self.username}: {str(e)}")
            self.page.screenshot(path=f'error_screenshot/comment_error_{self.username}_{int(time.time())}.png')
            return False

    def run(self):
        """Main worker loop"""
        if not self.initialize_browser():
            return

        try:
            while not self.stop_flag:
                if self.comment_queue.empty():
                    time.sleep(1)
                    continue

                video_url, comment = self.comment_queue.get()
                if self.post_comment(video_url, comment):
                    time.sleep(random.uniform(15, 30))  # Longer wait between comments for regular videos
                else:
                    # If posting fails, try to re-login once
                    self.is_logged_in = False
                    if self.login():
                        self.post_comment(video_url, comment)

        except Exception as e:
            logging.error(f"Worker error for {self.username}: {str(e)}")
        finally:
            if self.browser:
                self.browser.close()

    def stop(self):
        """Stop the worker"""
        self.stop_flag = True


class CommentManager:
    def __init__(self, accounts_file: str):
        with open(accounts_file, 'r') as f:
            self.accounts = json.load(f)
        self.workers = {}
        self.threads = {}
        self.setup_workers()

    def setup_workers(self):
        """Create workers for each account"""
        for account in self.accounts:
            worker = BrowserWorker(account)
            self.workers[account['username']] = worker
            thread = Thread(target=worker.run)
            self.threads[account['username']] = thread
            thread.start()

    def distribute_comments(self, video_url: str, comments: List[str]):
        """Distribute comments among workers"""
        available_workers = list(self.workers.values())
        random.shuffle(available_workers)  # Randomize worker order

        for i, comment in enumerate(comments):
            # Distribute comments round-robin style
            worker = available_workers[i % len(available_workers)]
            worker.comment_queue.put((video_url, comment))
            time.sleep(random.uniform(2, 5))  # Longer delay between distributions for regular videos

    def stop_all(self):
        """Stop all workers"""
        for worker in self.workers.values():
            worker.stop()
        for thread in self.threads.values():
            thread.join()


def load_comments(filename: str) -> List[str]:
    """Load comments from file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            comments = [line.strip() for line in f.readlines()]
            return [c for c in comments if c]
    except Exception as e:
        logging.error(f"Error loading comments: {str(e)}")
        return []

def main(ai_comments=None, ai_video_url=None):
    accounts_file = 'my_accounts.json'
    comments_file = 'comments.txt'
    if not ai_video_url:
        video_url = input("Enter the YouTube video URL: ")
        if not video_url:
            logging.error("No video URL provided. Exiting...")
            return
    else:
        video_url = ai_video_url

    if not ai_comments:
        comments = load_comments(comments_file)
        if not comments:
            logging.warning("No comments loaded. Using default comments.")
            comments = [
                "Great video!",
                "Thanks for sharing this!",
                "Very informative content!",
                "Keep up the great work!"
            ]

        random.shuffle(comments)  # Randomize comment order
    else:
        comments = ai_comments

    try:
        manager = CommentManager(accounts_file)
        manager.distribute_comments(video_url, comments)

        # Wait for all comments to be processed
        input("Press Enter to stop the program...\n")

    finally:
        manager.stop_all()



if __name__ == "__main__":
    main()