import json
import time
import random
import logging
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright


# Keep the BrowserWorker class mostly the same, just modify the comment posting logic
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
        """Setup logging configuration"""
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('youtube_comments.log'),
                    logging.StreamHandler()
                ]
            )

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

    async def initialize_browser(self):
        """Initialize browser with stealth settings"""
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

    async def login(self) -> bool:
        """Handle YouTube login process"""
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

    async def close(self):
        """Closes browser and cleanup"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def like_comment(self, comment_info: Dict) -> bool:
        """Like a specific comment using its link"""
        try:
            if not self.is_logged_in and not await self.login():
                return False

            if 'comment_link' not in comment_info:
                logging.error("No comment link provided")
                return False

            logging.info(f"Attempting to like comment as {self.username}")

            # Go directly to comment using the link
            await self.page.goto(comment_info['comment_link'])
            await self.page.wait_for_load_state('networkidle', timeout=60000)

            # Wait for comments to load and scroll to find the specific comment
            try:
                # Wait for initial comments to load
                await self.page.wait_for_selector('ytd-comments', timeout=10000)
                await asyncio.sleep(random.uniform(2, 3))

                # Scroll to comments section first
                await self.page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(random.uniform(1, 2))

                max_scroll_attempts = 10
                scroll_attempt = 0
                comment_thread = None

                while scroll_attempt < max_scroll_attempts:
                    try:
                        # Try to find the comment
                        comment_thread = await self.page.wait_for_selector('ytd-comment-thread-renderer', timeout=5000)
                        if comment_thread:
                            break
                    except:
                        # Scroll more if comment not found
                        await self.page.evaluate('window.scrollBy(0, 500)')
                        await asyncio.sleep(random.uniform(1, 2))
                        scroll_attempt += 1

                if not comment_thread:
                    logging.error(f"Could not find comment after {max_scroll_attempts} scroll attempts")
                    return False

                like_button = await comment_thread.wait_for_selector('#like-button button', timeout=5000)

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
                else:
                    logging.info(f"Comment already liked by {self.username}")
                    return True

            except Exception as e:
                logging.error(f"Error finding or liking comment: {str(e)}")
                return False

            return False

        except Exception as e:
            logging.error(f"Error liking comment as {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/like_error_{self.username}_{int(time.time())}.png')
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

            comment_box = await self.page.wait_for_selector('#placeholder-area', timeout=10000)
            await self.random_mouse_movement()
            await comment_box.click()
            await asyncio.sleep(random.uniform(1, 2))

            comment_input = await self.page.wait_for_selector('#contenteditable-root', timeout=10000)
            await self.type_humanlike(comment_input, comment)
            await asyncio.sleep(random.uniform(1, 2))

            submit_button = await self.page.wait_for_selector('#submit-button', timeout=10000)
            await self.random_mouse_movement()
            await submit_button.click()

            # Wait for comment to be posted
            await asyncio.sleep(random.uniform(4, 6))

            try:
                comment_element = await self.page.wait_for_selector(
                    'ytd-comment-thread-renderer:has-text("' + comment + '")', timeout=10000)
                timestamp_link = await comment_element.wait_for_selector('#published-time-text a', timeout=5000)

                href = await timestamp_link.get_attribute('href')
                if href:
                    comment_link = 'https://www.youtube.com' + href
                    logging.info(f"Successfully got comment link: {comment_link}")

                    return {
                        'comment_link': comment_link,
                        'comment_text': comment,
                        'author': self.username,
                        'timestamp': int(time.time())
                    }

            except Exception as e:
                logging.error(f"Error getting comment link: {str(e)}")
                await self.page.screenshot(path=f'error_screenshot/link_error_{self.username}_{int(time.time())}.png')
                return {}

        except Exception as e:
            logging.error(f"Error posting comment as {self.username}: {str(e)}")
            await self.page.screenshot(path=f'error_screenshot/comment_error_{self.username}_{int(time.time())}.png')
            return {}


class CommentManager:
    def __init__(self, accounts_file: str):
        with open(accounts_file, 'r') as f:
            self.accounts = json.load(f)
        self.workers = []
        self.comment_links = []

    def save_comment_links(self, filename: str = 'comment_links.json'):
        """Save comment links to JSON file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.comment_links, f, indent=4)
            logging.info(f"Comment links saved to {filename}")
        except Exception as e:
            logging.error(f"Error saving comment links: {str(e)}")

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

    async def post_comments(self, video_url: str, comments: List[str]):
        """Have each worker post one comment"""
        if len(comments) < len(self.workers):
            logging.warning("Not enough comments for all workers")
            return

        tasks = []
        for i, worker in enumerate(self.workers):
            if i < len(comments):
                tasks.append(self.post_single_comment(worker, video_url, comments[i]))
                # Add delay between starting each comment task
                await asyncio.sleep(random.uniform(5, 10))

        # Wait for all comments to be posted
        results = await asyncio.gather(*tasks)

        # Store successful comment links
        for result in results:
            if result:
                self.comment_links.append(result)

        # Save links to file
        self.save_comment_links()

    async def post_single_comment(self, worker: BrowserWorker, video_url: str, comment: str):
        """Post a single comment using a worker"""
        logging.info(f"Worker {worker.username} posting comment: {comment[:30]}...")
        return await worker.post_comment(video_url, comment)

    async def like_stored_comments(self):
        """Have all workers like all stored comments"""
        if not self.comment_links:
            logging.error("No comment links available to like")
            return

        for worker in self.workers:
            logging.info(f"Worker {worker.username} starting to like comments...")
            for comment_info in self.comment_links:
                # Don't like own comments
                if comment_info['author'] != worker.username:
                    success = await worker.like_comment(comment_info)
                    if success:
                        logging.info(f"Worker {worker.username} liked comment by {comment_info['author']}")
                    else:
                        logging.warning(f"Worker {worker.username} failed to like comment by {comment_info['author']}")
                    # Add delay between likes
                    await asyncio.sleep(random.uniform(3, 7))

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
        logging.error("No comments loaded. Exiting...")
        return

    try:
        # Initialize and run comment manager
        manager = CommentManager(accounts_file)
        await manager.setup_workers()

        # First phase: Post comments
        logging.info("Starting comment posting phase...")
        await manager.post_comments(video_url, comments)

        # Add delay between posting and liking phases
        await asyncio.sleep(random.uniform(30, 60))

        # Second phase: Like comments
        logging.info("Starting comment liking phase...")
        await manager.like_stored_comments()

    except KeyboardInterrupt:
        logging.info("Script interrupted by user. Closing all workers...")
    finally:
        await manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())