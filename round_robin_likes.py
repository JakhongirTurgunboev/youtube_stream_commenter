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
        self.playwright = None
        self.is_logged_in = False
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
                viewport={"width": 1920, "height": 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                ignore_https_errors=True
            )

            # Add stealth scripts
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            self.page = await self.context.new_page()

            # Try to login immediately after initialization
            if await self.login():
                return True
            return False

        except Exception as e:
            logging.error(f"Browser initialization error for {self.username}: {str(e)}")
            return False

    async def type_humanlike(self, element, text: str):
        """Types text with random delays between keystrokes to simulate human typing"""
        for char in text:
            await element.type(char, delay=random.randint(100, 300))
            await asyncio.sleep(random.uniform(0.1, 0.3))

    async def random_mouse_movement(self):
        """Simulates random mouse movements"""
        try:
            page_width = await self.page.evaluate('window.innerWidth')
            page_height = await self.page.evaluate('window.innerHeight')

            points = [
                (random.randint(0, page_width), random.randint(0, page_height))
                for _ in range(random.randint(2, 5))
            ]

            for x, y in points:
                await self.page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))

        except Exception as e:
            logging.warning(f"Mouse movement simulation failed: {str(e)}")

    async def login(self) -> bool:
        if self.is_logged_in:
            return True

        try:
            logging.info(f"Attempting to log in as {self.username}")
            await self.page.goto('https://www.youtube.com')
            await asyncio.sleep(random.uniform(2, 4))

            # Click sign in button
            await self.page.click('a[aria-label="Sign in"]')
            await asyncio.sleep(random.uniform(1, 2))

            # Type email
            email_input = await self.page.wait_for_selector('input[type="email"]')
            await self.random_mouse_movement()
            await self.type_humanlike(email_input, self.username)
            await asyncio.sleep(random.uniform(0.5, 1))
            await self.page.click('button:has-text("Next")')

            # Type password
            password_input = await self.page.wait_for_selector('input[type="password"]', state='visible')
            await self.random_mouse_movement()
            await self.type_humanlike(password_input, self.password)
            await asyncio.sleep(random.uniform(0.5, 1))
            await self.page.click('button:has-text("Next")')

            # Wait for successful login
            await self.page.wait_for_url('https://www.youtube.com/**')
            await asyncio.sleep(random.uniform(3, 5))

            # Verify login
            try:
                await self.page.wait_for_selector('#avatar-btn', timeout=10000)
                self.is_logged_in = True
                logging.info(f"Login successful for {self.username}")
                return True
            except Exception:
                logging.error(f"Login verification failed for {self.username}")
                return False

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

            # Scroll to comments section
            await self.page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(random.uniform(2, 4))

            # Find and click comment box
            comment_box = await self.page.wait_for_selector('#placeholder-area', timeout=10000)
            await self.random_mouse_movement()
            await comment_box.click()
            await asyncio.sleep(random.uniform(1, 2))

            # Type comment
            comment_input = await self.page.wait_for_selector('#contenteditable-root', timeout=10000)
            await self.type_humanlike(comment_input, comment)
            await asyncio.sleep(random.uniform(1, 2))

            # Get timestamp before posting
            timestamp = int(time.time())

            # Submit comment
            submit_button = await self.page.wait_for_selector('#submit-button', timeout=10000)
            await self.random_mouse_movement()
            await submit_button.click()

            # Wait for comment to be posted
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

            logging.info(f"Attempting to like comment as {self.username}")
            await self.page.goto(video_url)
            await self.page.wait_for_selector('video', timeout=60000)
            await self.page.wait_for_load_state('networkidle', timeout=60000)

            # Scroll to comments section
            await self.page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(random.uniform(2, 4))

            # Click sort button
            sort_button = await self.page.wait_for_selector('ytd-menu-renderer[id="sort-menu"] #button', timeout=10000)
            await self.random_mouse_movement()
            await sort_button.click()
            await asyncio.sleep(random.uniform(1, 2))

            # Select newest first
            newest_option = await self.page.wait_for_selector(
                '#items ytd-menu-service-item-renderer:has-text("Newest first")',
                timeout=10000
            )
            await self.random_mouse_movement()
            await newest_option.click()
            await asyncio.sleep(random.uniform(2, 4))

            # Calculate maximum age of comment to look for
            current_time = int(time.time())
            max_age = current_time - comment_info['timestamp']

            # Find and verify comment
            found = False
            max_scroll_attempts = 5
            scroll_attempt = 0

            while not found and scroll_attempt < max_scroll_attempts:
                comments = await self.page.query_selector_all('ytd-comment-thread-renderer')

                for comment in comments:
                    try:
                        author_elem = await comment.query_selector('#author-text')
                        text_elem = await comment.query_selector('#content-text')

                        if not author_elem or not text_elem:
                            continue

                        author = await author_elem.inner_text()
                        text = await text_elem.inner_text()

                        if (author.strip() == comment_info['author'] and
                                text.strip() == comment_info['comment_text']):

                            # Found matching comment, like it
                            like_button = await comment.query_selector('#like-button button')

                            if like_button:
                                # Check if already liked
                                aria_pressed = await like_button.get_attribute('aria-pressed')
                                if aria_pressed != 'true':
                                    await self.random_mouse_movement()
                                    await like_button.click()
                                    await asyncio.sleep(random.uniform(1, 2))

                                    # Verify like was registered
                                    aria_pressed = await like_button.get_attribute('aria-pressed')
                                    if aria_pressed == 'true':
                                        logging.info(f"Comment liked successfully by {self.username}")
                                        return True

                            found = True
                            break

                    except Exception as e:
                        logging.error(f"Error processing comment: {str(e)}")
                        continue

                if not found:
                    # Scroll down to load more comments
                    await self.page.evaluate('window.scrollBy(0, 1000)')
                    await asyncio.sleep(random.uniform(2, 3))
                    scroll_attempt += 1

            if not found:
                logging.warning(f"Comment not found for liking by {self.username}")
            return False

        except Exception as e:
            logging.error(f"Error liking comment as {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/like_error_{self.username}_{int(time.time())}.png')
            return False

    async def close(self):
        """Closes browser and cleanup"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


class CommentManager:
    def __init__(self, accounts_file: str):
        with open(accounts_file, 'r') as f:
            self.accounts = json.load(f)
        self.workers = []

    async def setup_workers(self):
        """Initialize all worker instances"""
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
        """Process comments using available workers"""
        if not self.workers or len(self.workers) < 2:
            logging.error("Need at least 2 workers (one for commenting, others for liking)")
            return

        comment_index = 0
        while comment_index < len(comments):
            # Select worker for commenting (round-robin)
            commenting_worker = self.workers[comment_index % len(self.workers)]
            comment = comments[comment_index]

            # Post comment and get info including timestamp
            comment_info = await commenting_worker.post_comment(video_url, comment)

            if comment_info:
                # Wait for comment to be indexed
                await asyncio.sleep(random.uniform(5, 10))

                # Have other workers like the comment
                like_tasks = []
                for worker in self.workers:
                    if worker != commenting_worker:
                        # Add random delay between likes to avoid rate limiting
                        await asyncio.sleep(random.uniform(2, 5))
                        like_tasks.append(worker.like_comment(video_url, comment_info))

                # Wait for all likes to complete
                if like_tasks:
                    results = await asyncio.gather(*like_tasks)
                    successful_likes = sum(1 for r in results if r)
                    logging.info(f"Comment received {successful_likes} likes out of {len(like_tasks)} attempts")

            comment_index += 1
            # Add longer delay between comments to avoid detection
            await asyncio.sleep(random.uniform(45, 90))

    async def close_all(self):
        """Close all worker instances"""
        await asyncio.gather(*[worker.close() for worker in self.workers])


def load_comments(filename: str) -> List[str]:
    """Load comments from file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except Exception as e:
        logging.error(f"Error loading comments: {str(e)}")
        return []


async def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('youtube_bot.log'),
            logging.StreamHandler()
        ]
    )

    accounts_file = 'accounts.json'
    comments_file = 'comments.txt'

    # Get video URL from user
    video_url = input("Enter the YouTube video URL: ")
    if not video_url:
        logging.error("No video URL provided. Exiting...")
        return

    # Load comments
    comments = load_comments(comments_file)
    if not comments:
        logging.warning("No comments loaded. Using default comments.")
        comments = [
            "Great video!",
            "Thanks for sharing!",
            "Very informative!",
            "Keep up the good work!",
            "Looking forward to more content!"
        ]

    try:
        # Initialize and run comment manager
        manager = CommentManager(accounts_file)
        await manager.setup_workers()
        await manager.process_comments(video_url, comments)
    except KeyboardInterrupt:
        logging.info("Script interrupted by user. Closing all workers...")
    finally:
        await manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())
    