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

    async def post_comment(self, video_url: str, comment: str) -> Dict:
        try:
            if not self.is_logged_in and not await self.login():
                return {}

            logging.info(f"Posting comment as {self.username}")
            await self.page.goto(video_url)
            await self.page.wait_for_selector('video', timeout=60000)
            await self.page.wait_for_load_state('networkidle', timeout=60000)

            # Scroll to comments
            await self.page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(random.uniform(2, 4))

            # Click comment box
            comment_box = self.page.locator('#placeholder-area')
            await comment_box.wait_for(state='visible', timeout=10000)
            await comment_box.click()
            await asyncio.sleep(random.uniform(1, 2))

            # Type comment
            comment_input = self.page.locator('#contenteditable-root')
            await comment_input.wait_for(state='visible', timeout=10000)
            await self.type_humanlike(comment_input, comment)

            # Get timestamp before posting
            timestamp = int(time.time())

            # Submit comment
            submit_button = self.page.locator('#submit-button')
            await submit_button.wait_for(state='visible', timeout=10000)
            await submit_button.click()

            # Wait for comment to appear
            await asyncio.sleep(random.uniform(4, 6))

            return {
                'timestamp': timestamp,
                'comment_text': comment,
                'author': self.username
            }

        except Exception as e:
            logging.error(f"Error posting comment as {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/comment_error_{self.username}_{int(time.time())}.png')
            return {}

    async def like_comment(self, video_url: str, comment_info: Dict) -> bool:
        try:
            if not self.is_logged_in and not await self.login():
                return False

            logging.info(f"Liking comment as {self.username}")
            await self.page.goto(video_url)
            await self.page.wait_for_selector('video', timeout=60000)

            # Scroll to comments
            await self.page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(random.uniform(2, 4))

            # Sort by newest
            sort_button = self.page.locator('yt-dropdown-menu #label:has-text("Sort by")')
            await sort_button.wait_for(state='visible', timeout=10000)
            await sort_button.click()
            await asyncio.sleep(random.uniform(1, 2))

            newest_option = self.page.locator('yt-formatted-string:has-text("Newest first")')
            await newest_option.wait_for(state='visible', timeout=10000)
            await newest_option.click()
            await asyncio.sleep(random.uniform(2, 4))

            # Find comment by text and author
            comments = self.page.locator('ytd-comment-thread-renderer')
            count = await comments.count()

            for i in range(min(10, count)):  # Check first 10 comments
                comment = comments.nth(i)
                author = await comment.locator('#author-text').inner_text()
                text = await comment.locator('#content-text').inner_text()

                if (author.strip() == comment_info['author'] and
                        text.strip() == comment_info['comment_text']):
                    # Found matching comment, like it
                    like_button = comment.locator('#like-button')
                    await like_button.wait_for(state='visible', timeout=10000)

                    # Check if already liked
                    aria_pressed = await like_button.get_attribute('aria-pressed')
                    if aria_pressed != 'true':
                        await like_button.click()
                        await asyncio.sleep(random.uniform(1, 2))

                        # Verify like was registered
                        aria_pressed = await like_button.get_attribute('aria-pressed')
                        if aria_pressed == 'true':
                            logging.info(f"Comment liked successfully by {self.username}")
                            return True

                    break

            logging.warning(f"Comment not found or like failed for {self.username}")
            return False

        except Exception as e:
            logging.error(f"Error liking comment as {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/like_error_{self.username}_{int(time.time())}.png')
            return False

    async def process_comments(self, video_url: str, comments: List[str]):
        if not self.workers or len(self.workers) < 2:
            logging.error("Need at least 2 workers (one for commenting, others for liking)")
            return

        comment_index = 0
        while comment_index < len(comments):
            commenting_worker = self.workers[comment_index % len(self.workers)]
            comment = comments[comment_index]

            # Post comment and get info
            comment_info = await commenting_worker.post_comment(video_url, comment)

            if comment_info:
                # Have other workers like the comment
                for worker in self.workers:
                    if worker != commenting_worker:
                        await worker.like_comment(video_url, comment_info)
                        await asyncio.sleep(random.uniform(2, 4))

            comment_index += 1
            await asyncio.sleep(random.uniform(30, 60))

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

        # Round-robin commenting and liking
        comment_index = 0
        while comment_index < len(comments):
            # Select the commenting worker (round-robin)
            commenting_worker = self.workers[comment_index % len(self.workers)]
            comment = comments[comment_index]

            # Post the comment
            comment_id = await commenting_worker.post_comment(video_url, comment)

            if comment_id:
                # Have all other workers like the comment
                for worker in self.workers:
                    if worker != commenting_worker:  # Skip the commenting worker
                        await worker.like_comment(video_url, comment_id)
                        await asyncio.sleep(random.uniform(2, 4))

            # Move to the next comment
            comment_index += 1
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
    