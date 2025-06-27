import asyncio
import json
from asyncio import Event
from bot_commenter import post_youtube_comments


async def example_usage():
    """Example of using the YouTube comment poster from external code"""

    # Define your accounts
    accounts = json.load(open("accounts.json"))

    # Define comments to post
    comments = [
        "This is an amazing video!",
        "Thanks for the great content!",
        "Really helpful, appreciate it!",
        "Looking forward to more videos like this!",
        "Excellent explanation!"
    ]

    # Video URL
    video_url = "https://www.youtube.com/watch?v=Wc_Ql74qyHQ"

    # Create a stop event (optional)
    stop_event = Event()

    # Example 1: Run without interruption
    print("Starting comment posting...")
    stats = await post_youtube_comments(video_url, comments, accounts)

    print(f"\nResults:")
    print(f"Success: {stats['total']['successful_posts']} comments posted")
    print(f"Failed: {stats['total']['failed_posts']} comments failed")
    print(f"Total attempts: {stats['total']['total_attempts']}")

    # Example 2: Run with ability to stop after 30 seconds
    async def stop_after_delay(event: Event, delay: int):
        await asyncio.sleep(delay)
        print(f"\nStopping after {delay} seconds...")
        event.set()

    stop_event = Event()

    # Run posting and timer concurrently
    posting_task = asyncio.create_task(
        post_youtube_comments(video_url, comments, accounts, stop_event)
    )
    timer_task = asyncio.create_task(stop_after_delay(stop_event, 30))

    # Wait for posting to complete (or be stopped)
    stats = await posting_task
    timer_task.cancel()

    print(f"\nResults after early stop:")
    print(f"Stopped early: {stats['total']['stopped_early']}")
    print(f"Success: {stats['total']['successful_posts']} comments posted")
    print(f"Failed: {stats['total']['failed_posts']} comments failed")


async def advanced_usage():
    """Advanced example with multiple videos and dynamic stop control"""

    accounts = [
        {"username": "user1@gmail.com", "password": "password1"},
        {"username": "user2@gmail.com", "password": "password2"}
    ]

    videos_and_comments = [
        {
            "url": "https://www.youtube.com/watch?v=VIDEO1",
            "comments": ["Great tutorial!", "Very helpful!"]
        },
        {
            "url": "https://www.youtube.com/watch?v=VIDEO2",
            "comments": ["Amazing content!", "Thanks for sharing!"]
        }
    ]

    all_stats = []

    for video_data in videos_and_comments:
        print(f"\nPosting to {video_data['url']}...")

        # Create a new stop event for each video
        stop_event = Event()

        # Post comments
        stats = await post_youtube_comments(
            video_data['url'],
            video_data['comments'],
            accounts,
            stop_event
        )

        all_stats.append({
            "video": video_data['url'],
            "stats": stats
        })

        # Wait between videos
        await asyncio.sleep(5)

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY OF ALL VIDEOS")
    print("=" * 50)

    total_success = sum(s['stats']['total']['successful_posts'] for s in all_stats)
    total_failed = sum(s['stats']['total']['failed_posts'] for s in all_stats)

    print(f"Total videos processed: {len(all_stats)}")
    print(f"Total successful comments: {total_success}")
    print(f"Total failed comments: {total_failed}")

    for stat_data in all_stats:
        print(f"\n{stat_data['video']}:")
        print(f"  - Success: {stat_data['stats']['total']['successful_posts']}")
        print(f"  - Failed: {stat_data['stats']['total']['failed_posts']}")


# Integration with existing async application
class YouTubeCommentService:
    """Service class for integrating with larger applications"""

    def __init__(self, accounts: list):
        self.accounts = accounts
        self.active_tasks = {}

    async def post_comments_with_tracking(
            self,
            task_id: str,
            video_url: str,
            comments: list
    ) -> dict:
        """Post comments with task tracking"""

        stop_event = Event()
        self.active_tasks[task_id] = stop_event

        try:
            stats = await post_youtube_comments(
                video_url,
                comments,
                self.accounts,
                stop_event
            )
            return {
                "task_id": task_id,
                "status": "completed",
                "stats": stats
            }
        finally:
            self.active_tasks.pop(task_id, None)

    def stop_task(self, task_id: str) -> bool:
        """Stop a specific task"""
        if task_id in self.active_tasks:
            self.active_tasks[task_id].set()
            return True
        return False

    def stop_all_tasks(self):
        """Stop all active tasks"""
        for stop_event in self.active_tasks.values():
            stop_event.set()


# Example of using the service
async def service_example():
    accounts = [
        {"username": "user1@gmail.com", "password": "password1"},
        {"username": "user2@gmail.com", "password": "password2"}
    ]

    service = YouTubeCommentService(accounts)

    # Start a task
    task = asyncio.create_task(
        service.post_comments_with_tracking(
            "task_001",
            "https://www.youtube.com/watch?v=Wc_Ql74qyHQ",
            ["Comment 1", "Comment 2", "Comment 3"]
        )
    )

    # Simulate stopping after 20 seconds
    await asyncio.sleep(20)
    service.stop_task("task_001")

    # Get results
    result = await task
    print(f"Task {result['task_id']} status: {result['status']}")
    print(f"Comments posted: {result['stats']['total']['successful_posts']}")


if __name__ == "__main__":
    # Run basic example
    asyncio.run(example_usage())

    # Uncomment to run other examples
    # asyncio.run(advanced_usage())
    # asyncio.run(service_example())