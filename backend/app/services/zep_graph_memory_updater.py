"""
Zep graph memory update service.

Streams agent activity from running simulations into the Zep knowledge graph.
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from .graphiti_adapter import GraphitiAdapter

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_locale, set_locale, t

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Record of a single agent activity."""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """Render the activity as a natural-language episode for Zep.

        The text uses plain narrative phrasing so Zep can extract entities and
        relationships from it. No simulation-specific prefix is prepended, so
        the graph update is not biased by framing words.
        """
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()

        # Return "<agent name>: <activity>" with no simulation prefix.
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"发布了一条帖子：「{content}」"
        return "发布了一条帖子"
    
    def _describe_like_post(self) -> str:
        """Like a post — includes the post text and author when available."""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"点赞了{post_author}的帖子：「{post_content}」"
        elif post_content:
            return f"点赞了一条帖子：「{post_content}」"
        elif post_author:
            return f"点赞了{post_author}的一条帖子"
        return "点赞了一条帖子"
    
    def _describe_dislike_post(self) -> str:
        """Dislike a post — includes the post text and author when available."""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"踩了{post_author}的帖子：「{post_content}」"
        elif post_content:
            return f"踩了一条帖子：「{post_content}」"
        elif post_author:
            return f"踩了{post_author}的一条帖子"
        return "踩了一条帖子"
    
    def _describe_repost(self) -> str:
        """Repost — includes the original post text and author when available."""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"转发了{original_author}的帖子：「{original_content}」"
        elif original_content:
            return f"转发了一条帖子：「{original_content}」"
        elif original_author:
            return f"转发了{original_author}的一条帖子"
        return "转发了一条帖子"
    
    def _describe_quote_post(self) -> str:
        """Quote-post — includes the original post, author, and the quote comment."""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"引用了{original_author}的帖子「{original_content}」"
        elif original_content:
            base = f"引用了一条帖子「{original_content}」"
        elif original_author:
            base = f"引用了{original_author}的一条帖子"
        else:
            base = "引用了一条帖子"
        
        if quote_content:
            base += f"，并评论道：「{quote_content}」"
        return base
    
    def _describe_follow(self) -> str:
        """Follow a user — includes the followed user's name."""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"关注了用户「{target_user_name}」"
        return "关注了一个用户"
    
    def _describe_create_comment(self) -> str:
        """Create a comment — includes the comment text and the parent post."""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"在{post_author}的帖子「{post_content}」下评论道：「{content}」"
            elif post_content:
                return f"在帖子「{post_content}」下评论道：「{content}」"
            elif post_author:
                return f"在{post_author}的帖子下评论道：「{content}」"
            return f"评论道：「{content}」"
        return "发表了评论"
    
    def _describe_like_comment(self) -> str:
        """Like a comment — includes the comment text and author when available."""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"点赞了{comment_author}的评论：「{comment_content}」"
        elif comment_content:
            return f"点赞了一条评论：「{comment_content}」"
        elif comment_author:
            return f"点赞了{comment_author}的一条评论"
        return "点赞了一条评论"
    
    def _describe_dislike_comment(self) -> str:
        """Dislike a comment — includes the comment text and author when available."""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"踩了{comment_author}的评论：「{comment_content}」"
        elif comment_content:
            return f"踩了一条评论：「{comment_content}」"
        elif comment_author:
            return f"踩了{comment_author}的一条评论"
        return "踩了一条评论"
    
    def _describe_search(self) -> str:
        """Search posts — includes the search query."""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"搜索了「{query}」" if query else "进行了搜索"
    
    def _describe_search_user(self) -> str:
        """Search users — includes the search query."""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"搜索了用户「{query}」" if query else "搜索了用户"
    
    def _describe_mute(self) -> str:
        """Mute a user — includes the muted user's name."""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"屏蔽了用户「{target_user_name}」"
        return "屏蔽了一个用户"
    
    def _describe_generic(self) -> str:
        # Fallback narration for action types not handled explicitly above.
        return f"执行了{self.action_type}操作"


class ZepGraphMemoryUpdater:
    """Zep graph memory updater.

    Watches a simulation's actions log file and streams new agent activity
    into the Zep knowledge graph in near real time. Activities are grouped
    by platform; each platform sends a batch once it has accumulated
    ``BATCH_SIZE`` items.

    Every meaningful action is forwarded to Zep, with full context preserved
    in ``action_args``:

    - Original text of liked / disliked posts
    - Original text of reposted / quoted posts
    - Names of followed / muted users
    - Original text of liked / disliked comments
    """
    
    # Number of activities to accumulate per platform before sending a batch.
    BATCH_SIZE = 5

    # Platform display names used for console / log output.
    PLATFORM_DISPLAY_NAMES = {
        'twitter': '世界1',
        'reddit': '世界2',
    }

    # Pause between sends (seconds) to avoid hammering the Zep API.
    SEND_INTERVAL = 0.5

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """Initialize the updater.

        Args:
            graph_id: Zep graph ID.
            api_key: Optional Zep API key; defaults to the value from config.
        """
        self.graph_id = graph_id
        self.client = GraphitiAdapter()

        self._activity_queue: Queue = Queue()

        # Per-platform buffer; each platform flushes once it reaches BATCH_SIZE.
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()

        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        # Counters
        self._total_activities = 0  # activities accepted into the queue
        self._total_sent = 0        # batches successfully sent to Zep
        self._total_items_sent = 0  # individual activities successfully sent to Zep
        self._failed_count = 0      # batches that failed to send
        self._skipped_count = 0     # activities filtered out (e.g. DO_NOTHING)
        
        logger.info(t("log.zep_graph_memory_updater.m001", graph_id=graph_id, self=self.BATCH_SIZE))
    
    def _get_platform_display_name(self, platform: str) -> str:
        """Return the human-friendly display name for a platform."""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """Start the background worker thread."""
        if self._running:
            return

        # Capture locale before spawning background thread
        current_locale = get_locale()

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(current_locale,),
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(t("log.zep_graph_memory_updater.m002", self=self.graph_id))
    
    def stop(self):
        """Stop the background worker thread and flush pending activity."""
        self._running = False

        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(t("log.zep_graph_memory_updater.m003", self=self.graph_id, self_2=self._total_activities, self_3=self._total_sent, self_4=self._total_items_sent, self_5=self._failed_count, self_6=self._skipped_count))
    
    def add_activity(self, activity: AgentActivity):
        """Enqueue a single agent activity for delivery to Zep.

        Every meaningful action is queued, including:

        - CREATE_POST (post)
        - CREATE_COMMENT (comment)
        - QUOTE_POST (quote a post)
        - SEARCH_POSTS (search posts)
        - SEARCH_USER (search users)
        - LIKE_POST / DISLIKE_POST (like / dislike a post)
        - REPOST (repost)
        - FOLLOW (follow)
        - MUTE (mute)
        - LIKE_COMMENT / DISLIKE_COMMENT (like / dislike a comment)

        ``action_args`` carries the full context (e.g. original post text,
        user names) so the graph episode is self-contained.

        Args:
            activity: The agent activity record to enqueue.
        """
        # DO_NOTHING actions carry no information worth indexing.
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(t("log.zep_graph_memory_updater.m004", activity=activity.agent_name, activity_2=activity.action_type))
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """Build an ``AgentActivity`` from a parsed JSON record and enqueue it.

        Args:
            data: A dict parsed from a single ``actions.jsonl`` line.
            platform: Source platform name (``twitter`` or ``reddit``).
        """
        # Event-type rows describe simulation lifecycle, not agent activity.
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self, locale: str = 'zh'):
        """Background loop that drains the queue and flushes per-platform batches."""
        set_locale(locale)
        while self._running or not self._activity_queue.empty():
            try:
                # Block briefly so the loop can also notice shutdown requests.
                try:
                    activity = self._activity_queue.get(timeout=1)

                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)

                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # Release the lock before issuing the network call.
                            self._send_batch_activities(batch, platform)
                            # Throttle so we don't hammer the Zep API.
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(t("log.zep_graph_memory_updater.m005", e=e))
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """Send a batch of activities to the Zep graph as one combined episode.

        Args:
            activities: Agent activity records to send.
            platform: Source platform name.
        """
        if not activities:
            return

        # Concatenate the per-activity narrations into a single newline-separated episode.
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)

        # Retry on failure with linear backoff.
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(t("log.zep_graph_memory_updater.m006", len=len(activities), display_name=display_name, self=self.graph_id))
                logger.debug(t("log.zep_graph_memory_updater.m007", combined_text=combined_text[:200]))
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(t("log.zep_graph_memory_updater.m008", attempt=attempt + 1, self=self.MAX_RETRIES, e=e))
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(t("log.zep_graph_memory_updater.m009", self=self.MAX_RETRIES, e=e))
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """Drain the queue and flush every platform buffer, even partial ones."""
        # Move anything still in the queue into the per-platform buffers.
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break

        # Flush each platform buffer regardless of whether it reached BATCH_SIZE.
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(t("log.zep_graph_memory_updater.m010", display_name=display_name, len=len(buffer)))
                    self._send_batch_activities(buffer, platform)
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of updater statistics."""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}

        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # activities accepted into the queue
            "batches_sent": self._total_sent,            # batches successfully sent
            "items_sent": self._total_items_sent,        # activities successfully sent
            "failed_count": self._failed_count,          # batches that failed to send
            "skipped_count": self._skipped_count,        # activities filtered out (e.g. DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # per-platform buffer depth
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """Registry that owns one ``ZepGraphMemoryUpdater`` per active simulation."""
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """Create (and start) a graph-memory updater for a simulation.

        Args:
            simulation_id: Simulation ID.
            graph_id: Zep graph ID.

        Returns:
            The started ``ZepGraphMemoryUpdater`` instance.
        """
        with cls._lock:
            # An updater already exists for this simulation — stop it first.
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(t("log.zep_graph_memory_updater.m011", simulation_id=simulation_id, graph_id=graph_id))
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Return the updater for a simulation, or ``None`` if absent."""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """Stop and deregister the updater belonging to a simulation."""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(t("log.zep_graph_memory_updater.m012", simulation_id=simulation_id))
    
    # Idempotency guard so ``stop_all`` only runs once per process lifetime.
    _stop_all_done = False

    @classmethod
    def stop_all(cls):
        """Stop every registered updater (idempotent)."""
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(t("log.zep_graph_memory_updater.m013", simulation_id=simulation_id, e=e))
                cls._updaters.clear()
            logger.info(t("log.zep_graph_memory_updater.m014"))
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Return statistics for every registered updater."""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
