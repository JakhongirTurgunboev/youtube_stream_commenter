import json
import time
import random
import logging
import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, Page, BrowserContext, Browser
from asyncio import Event, Queue


@dataclass
class CommentStats:
    """Statistics for comment posting"""
    total_attempts: int = 0
    successful_posts: int = 0
    failed_posts: int = 0
    login_failures: int = 0
    stopped_early: bool = False
    errors: List[Dict[str, str]] = field(default_factory=list)


class AsyncBrowserWorker:
    def __init__(self, account: Dict, stop_event: Event):
        self.account = account
        self.username = account['username']
        self.password = account['password']
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        self.comment_queue: Queue = Queue()
        self.stop_event = stop_event
        self.stats = CommentStats()
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

    async def initialize_browser(self) -> bool:
        """Initialize browser session"""
        if self.stop_event.is_set():
            return False

        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-sandbox',
                    '--disable-web-security'
                ]
            )

            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation', 'notifications'],
                ignore_https_errors=True
            )

            self.page = await self.context.new_page()
            return True
        except Exception as e:
            error_msg = f"Browser initialization error for {self.username}: {str(e)}"
            logging.error(error_msg)
            self.stats.errors.append({"username": self.username, "error": error_msg})
            return False

    async def type_humanlike(self, selector: str, text: str):
        """Type with human-like delays"""
        if self.stop_event.is_set():
            return

        for char in text:
            if self.stop_event.is_set():
                return
            await self.page.type(selector, char, delay=random.randint(100, 300))
            await asyncio.sleep(random.uniform(0.1, 0.3))

    async def login(self) -> bool:
        """Perform login once"""
        if self.is_logged_in:
            return True

        if self.stop_event.is_set():
            return False

        try:
            logging.info(f"Logging in {self.username}")
            await self.page.goto('https://www.youtube.com')
            await asyncio.sleep(random.uniform(2, 4))

            if self.stop_event.is_set():
                return False

            await self.page.click('a[aria-label="Sign in"]')
            await self.page.wait_for_selector('input[type="email"]')
            await self.type_humanlike('input[type="email"]', self.username)
            await self.page.click('button:has-text("Next")')

            if self.stop_event.is_set():
                return False

            await self.page.wait_for_selector('input[type="password"]', state='visible')
            await self.type_humanlike('input[type="password"]', self.password)
            await self.page.click('button:has-text("Next")')

            await self.page.wait_for_url('https://www.youtube.com/**')
            await asyncio.sleep(random.uniform(3, 5))

            self.is_logged_in = True
            logging.info(f"Login successful for {self.username}")
            return True

        except Exception as e:
            error_msg = f"Login error for {self.username}: {str(e)}"
            logging.error(error_msg)
            self.stats.login_failures += 1
            self.stats.errors.append({"username": self.username, "error": error_msg})

            try:
                await self.page.screenshot(path=f'error_screenshot/login_error_{self.username}_{int(time.time())}.png')
            except:
                pass

            return False

    async def post_comment(self, video_url: str, comment: str) -> bool:
        """Post a single comment on a video"""
        if self.stop_event.is_set():
            return False

        try:
            if not self.is_logged_in and not await self.login():
                return False

            if self.stop_event.is_set():
                return False

            logging.info(f"Navigating to video as {self.username}")
            await self.page.goto(video_url)
            await self.page.wait_for_selector('video', timeout=60000)
            await self.page.wait_for_load_state('networkidle', timeout=60000)

            if self.stop_event.is_set():
                return False

            # Scroll to comments section
            await self.page.evaluate('''() => {
                window.scrollBy(0, window.innerHeight);
            }''')
            await asyncio.sleep(random.uniform(2, 4))

            # Wait for and click on comment box
            comment_box = self.page.locator('#simplebox-placeholder')
            await comment_box.wait_for(state='visible', timeout=10000)
            await comment_box.click()
            await asyncio.sleep(random.uniform(1, 2))

            if self.stop_event.is_set():
                return False

            # Type the comment
            comment_input = self.page.locator('#contenteditable-root')
            await comment_input.wait_for(state='visible', timeout=10000)

            for char in comment:
                if self.stop_event.is_set():
                    return False
                await comment_input.type(char, delay=random.randint(50, 200))

            await asyncio.sleep(random.uniform(1, 2))

            # Click submit button
            submit_button = self.page.locator('#submit-button')
            await submit_button.wait_for(state='visible', timeout=10000)
            await submit_button.click()

            # Wait for comment to be posted
            await asyncio.sleep(random.uniform(2, 4))

            logging.info(f"Comment posted successfully as {self.username}")
            self.stats.successful_posts += 1
            return True

        except Exception as e:
            error_msg = f"Error posting comment as {self.username}: {str(e)}"
            logging.error(error_msg)
            self.stats.failed_posts += 1
            self.stats.errors.append({"username": self.username, "error": error_msg})

            try:
                await self.page.screenshot(
                    path=f'error_screenshot/comment_error_{self.username}_{int(time.time())}.png')
            except:
                pass

            return False

    async def run(self):
        """Main worker loop"""
        if not await self.initialize_browser():
            return

        try:
            while not self.stop_event.is_set():
                try:
                    video_url, comment = await asyncio.wait_for(
                        self.comment_queue.get(),
                        timeout=1.0
                    )

                    self.stats.total_attempts += 1

                    if await self.post_comment(video_url, comment):
                        await asyncio.sleep(random.uniform(15, 30))
                    else:
                        # If posting fails, try to re-login once
                        self.is_logged_in = False
                        if await self.login():
                            if await self.post_comment(video_url, comment):
                                self.stats.successful_posts -= 1  # Correct the double count
                                await asyncio.sleep(random.uniform(15, 30))

                except asyncio.TimeoutError:
                    continue

        except Exception as e:
            error_msg = f"Worker error for {self.username}: {str(e)}"
            logging.error(error_msg)
            self.stats.errors.append({"username": self.username, "error": error_msg})
        finally:
            if self.browser:
                await self.browser.close()

    def get_stats(self) -> CommentStats:
        """Get worker statistics"""
        if self.stop_event.is_set():
            self.stats.stopped_early = True
        return self.stats


class AsyncCommentManager:
    def __init__(self, accounts: List[Dict], stop_event: Event):
        self.accounts = accounts
        self.workers: Dict[str, AsyncBrowserWorker] = {}
        self.tasks: List[asyncio.Task] = []
        self.stop_event = stop_event

    async def setup_workers(self):
        """Create workers for each account"""
        for account in self.accounts:
            worker = AsyncBrowserWorker(account, self.stop_event)
            self.workers[account['username']] = worker
            task = asyncio.create_task(worker.run())
            self.tasks.append(task)

    async def distribute_comments(self, video_url: str, comments: List[str]):
        """Distribute comments among workers"""
        available_workers = list(self.workers.values())
        random.shuffle(available_workers)

        for i, comment in enumerate(comments):
            if self.stop_event.is_set():
                break

            worker = available_workers[i % len(available_workers)]
            await worker.comment_queue.put((video_url, comment))
            await asyncio.sleep(random.uniform(2, 5))

    async def get_all_stats(self) -> Dict[str, any]:
        """Collect statistics from all workers"""
        total_stats = CommentStats()
        worker_stats = {}

        for username, worker in self.workers.items():
            stats = worker.get_stats()
            worker_stats[username] = {
                "total_attempts": stats.total_attempts,
                "successful_posts": stats.successful_posts,
                "failed_posts": stats.failed_posts,
                "login_failures": stats.login_failures
            }

            total_stats.total_attempts += stats.total_attempts
            total_stats.successful_posts += stats.successful_posts
            total_stats.failed_posts += stats.failed_posts
            total_stats.login_failures += stats.login_failures
            total_stats.errors.extend(stats.errors)

            if stats.stopped_early:
                total_stats.stopped_early = True

        return {
            "total": {
                "accounts_used": len(self.workers),
                "total_attempts": total_stats.total_attempts,
                "successful_posts": total_stats.successful_posts,
                "failed_posts": total_stats.failed_posts,
                "login_failures": total_stats.login_failures,
                "stopped_early": total_stats.stopped_early
            },
            "by_account": worker_stats,
            "errors": total_stats.errors
        }

    async def stop_all(self):
        """Stop all workers"""
        self.stop_event.set()
        await asyncio.gather(*self.tasks, return_exceptions=True)


async def post_youtube_comments(
        video_url: str,
        comments: List[str],
        accounts: List[Dict],
        stop_event: Optional[Event] = None
) -> Dict[str, any]:
    """
    Main async function to post YouTube comments

    Args:
        video_url: YouTube video URL
        comments: List of comments to post
        accounts: List of account dictionaries with 'username' and 'password'
        stop_event: Optional event to stop the process early

    Returns:
        Dictionary with statistics about the posting process
    """
    if stop_event is None:
        stop_event = Event()

    manager = AsyncCommentManager(accounts, stop_event)

    try:
        await manager.setup_workers()
        await manager.distribute_comments(video_url, comments)

        # Wait for all comments to be processed or stop event
        while not stop_event.is_set():
            # Check if all queues are empty
            all_empty = all(worker.comment_queue.empty() for worker in manager.workers.values())
            if all_empty:
                # Give some time for last comments to be posted
                await asyncio.sleep(5)
                break
            await asyncio.sleep(1)

    finally:
        stats = await manager.get_all_stats()
        await manager.stop_all()

    return stats


def load_accounts(filename: str) -> List[Dict]:
    """Load accounts from JSON file"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading accounts: {str(e)}")
        return []


def load_comments(filename: str) -> List[str]:
    """Load comments from file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            comments = [line.strip() for line in f.readlines()]
            return [c for c in comments if c]
    except Exception as e:
        logging.error(f"Error loading comments: {str(e)}")
        return []


async def main():
    """Test function for standalone execution"""
    accounts_file = 'my_accounts.json'
    comments_file = 'comments.txt'

    video_url = input("Enter the YouTube video URL: ")
    if not video_url:
        logging.error("No video URL provided. Exiting...")
        return

    accounts = load_accounts(accounts_file)
    if not accounts:
        logging.error("No accounts loaded. Exiting...")
        return

    comments = load_comments(comments_file)
    if not comments:
        logging.warning("No comments loaded. Using default comments.")
        comments = [
            "Great video!",
            "Thanks for sharing this!",
            "Very informative content!",
            "Keep up the great work!"
        ]

    random.shuffle(comments)

    # Create stop event for manual interruption
    stop_event = Event()

    async def wait_for_enter():
        await asyncio.get_event_loop().run_in_executor(
            None, input, "Press Enter to stop the program...\n"
        )
        stop_event.set()

    # Run comment posting and wait for enter concurrently
    posting_task = asyncio.create_task(
        post_youtube_comments(video_url, comments, accounts, stop_event)
    )
    wait_task = asyncio.create_task(wait_for_enter())

    # Wait for either completion or manual stop
    done, pending = await asyncio.wait(
        [posting_task, wait_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    # If posting finished first, cancel the wait
    if posting_task in done:
        wait_task.cancel()
        stats = posting_task.result()
    else:
        # If enter was pressed, wait for posting to finish
        stats = await posting_task

    # Print statistics
    print("\n" + "=" * 50)
    print("POSTING STATISTICS")
    print("=" * 50)
    print(f"Total accounts used: {stats['total']['accounts_used']}")
    print(f"Total attempts: {stats['total']['total_attempts']}")
    print(f"Successful posts: {stats['total']['successful_posts']}")
    print(f"Failed posts: {stats['total']['failed_posts']}")
    print(f"Login failures: {stats['total']['login_failures']}")
    print(f"Stopped early: {stats['total']['stopped_early']}")

    if stats['errors']:
        print("\nErrors encountered:")
        for error in stats['errors'][:5]:  # Show first 5 errors
            print(f"  - {error['username']}: {error['error']}")
        if len(stats['errors']) > 5:
            print(f"  ... and {len(stats['errors']) - 5} more errors")


if __name__ == "__main__":
    asyncio.run(main())