import json
import time
import random
import logging
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright


class BrowserWorker:
    def __init__(self, account: Dict):
        self.account = account
        self.username = account['username']
        self.password = account['password']
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
        self.setup_logging()

    def setup_logging(self):
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                                handlers=[logging.FileHandler('youtube_comments.log'), logging.StreamHandler()])

    async def initialize_browser(self):
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                ignore_https_errors=True
            )
            self.page = await self.context.new_page()

            # Try to login immediately after initialization
            if await self.login():
                return True
            return False
        except Exception as e:
            logging.error(f"Browser initialization error for {self.username}: {str(e)}")
            return False

    async def type_humanlike(self, element, text: str):
        for char in text:
            await element.type(char, delay=random.randint(100, 300))
            await asyncio.sleep(random.uniform(0.1, 0.3))

    async def login(self) -> bool:
        if self.is_logged_in:
            return True

        try:
            logging.info(f"Logging in {self.username}")
            await self.page.goto('https://www.youtube.com')
            await asyncio.sleep(random.uniform(2, 4))

            await self.page.click('a[aria-label="Sign in"]')
            email_input = await self.page.wait_for_selector('input[type="email"]')
            await self.type_humanlike(email_input, self.username)
            await self.page.click('button:has-text("Next")')

            password_input = await self.page.wait_for_selector('input[type="password"]', state='visible')
            await self.type_humanlike(password_input, self.password)
            await self.page.click('button:has-text("Next")')

            await self.page.wait_for_url('https://www.youtube.com/**')
            await asyncio.sleep(random.uniform(3, 5))

            self.is_logged_in = True
            logging.info(f"Login successful for {self.username}")
            return True

        except Exception as e:
            logging.error(f"Login error for {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/login_error_{self.username}_{int(time.time())}.png')
            return False

    async def post_comment(self, video_url: str, comment: str) -> str:
        try:
            if not self.is_logged_in and not await self.login():
                return ""

            logging.info(f"Posting comment as {self.username}")
            await self.page.goto(video_url)
            await self.page.wait_for_selector('video', timeout=60000)
            await self.page.wait_for_load_state('networkidle', timeout=60000)

            # Scroll down to the comments section
            await self.page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(random.uniform(2, 4))

            # Click the comment box
            comment_box = self.page.locator('#placeholder-area')
            await comment_box.wait_for(state='visible', timeout=10000)
            await comment_box.click()
            await asyncio.sleep(random.uniform(1, 2))

            # Type the comment
            comment_input = self.page.locator('#contenteditable-root')
            await comment_input.wait_for(state='visible', timeout=10000)
            await self.type_humanlike(comment_input, comment)

            # Submit the comment
            submit_button = self.page.locator('#submit-button')
            await submit_button.wait_for(state='visible', timeout=10000)
            await submit_button.click()

            # Wait for the comment to be posted
            await asyncio.sleep(random.uniform(4, 6))

            # Capture the comment ID
            latest_comments = self.page.locator('ytd-comment-thread-renderer')
            first_comment = latest_comments.first
            comment_id = await first_comment.get_attribute('id')

            logging.info(f"Comment posted successfully by {self.username}. Comment ID: {comment_id}")
            return comment_id

        except Exception as e:
            logging.error(f"Error posting comment as {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/comment_error_{self.username}_{int(time.time())}.png')
            return ""

    async def like_comment(self, video_url: str, comment_id: str) -> bool:
        try:
            if not self.is_logged_in and not await self.login():
                return False

            logging.info(f"Liking comment as {self.username}")
            await self.page.goto(video_url)
            await self.page.wait_for_url(video_url, timeout=60000)  # Ensure navigation to the video URL
            await self.page.wait_for_selector('video', timeout=60000)

            # Scroll down to the comments section
            await self.page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(random.uniform(2, 4))

            # Wait for the comments section to load
            await self.page.wait_for_selector('ytd-comment-thread-renderer', timeout=10000)

            # Find the comment by ID
            comment = self.page.locator(f'ytd-comment-thread-renderer#{comment_id}')
            await comment.wait_for(state='visible', timeout=10000)

            # Find the like button inside the comment
            like_button = comment.locator('#like-button')
            await like_button.wait_for(state='visible', timeout=10000)
            await like_button.click()

            await asyncio.sleep(random.uniform(1, 2))
            logging.info(f"Comment liked successfully by {self.username}")
            return True

        except Exception as e:
            logging.error(f"Error liking comment as {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/like_error_{self.username}_{int(time.time())}.png')
            return False

    async def close(self):
        if self.browser:
            await self.browser.close()


class CommentManager:
    def __init__(self, accounts_file: str):
        with open(accounts_file, 'r') as f:
            self.accounts = json.load(f)
        self.workers = []

    async def setup_workers(self):
        logging.info(f"Setting up {len(self.accounts)} workers...")
        for account in self.accounts:
            worker = BrowserWorker(account)
            if await worker.initialize_browser():
                self.workers.append(worker)
                logging.info(f"Worker {worker.username} initialized successfully")
            else:
                logging.error(f"Failed to initialize worker for {account['username']}")

        logging.info(f"Successfully initialized {len(self.workers)} workers")

    async def process_comments(self, video_url: str, comments: List[str]):
        if not self.workers or len(self.workers) < 2:
            logging.error("Need at least 2 workers (one for commenting, others for liking)")
            return

        # First worker will be dedicated to commenting
        commenting_worker = self.workers[0]
        liking_workers = self.workers[1:]

        while True:
            for comment in comments:
                # Post comment with the dedicated commenting worker
                comment_id = await commenting_worker.post_comment(video_url, comment)

                if comment_id:
                    # Have all other workers like the comment
                    await asyncio.sleep(random.uniform(2, 4))
                    for worker in liking_workers:
                        await worker.like_comment(video_url, comment_id)
                        await asyncio.sleep(random.uniform(2, 4))

                # Wait for a random interval before posting the next comment
                await asyncio.sleep(random.uniform(30, 60))

    async def close_all(self):
        await asyncio.gather(*[worker.close() for worker in self.workers])


def load_comments(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except Exception as e:
        logging.error(f"Error loading comments: {str(e)}")
        return []


async def main():
    accounts_file = 'accounts.json'
    comments_file = 'comments.txt'

    video_url = input("Enter the YouTube video URL: ")
    if not video_url:
        logging.error("No video URL provided. Exiting...")
        return

    comments = load_comments(comments_file)
    if not comments:
        logging.warning("No comments loaded. Using default comments.")
        comments = [
            "Great video!", "Thanks for sharing!",
            "Very informative!", "Keep it up!"
        ]

    try:
        manager = CommentManager(accounts_file)
        await manager.setup_workers()
        await manager.process_comments(video_url, comments)
    except KeyboardInterrupt:
        logging.info("Script interrupted by user. Closing all workers...")
    finally:
        await manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())