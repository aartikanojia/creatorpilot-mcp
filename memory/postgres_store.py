"""
PostgreSQL-based long-term memory store.

Provides persistent storage for:
- Analytics snapshots
- Weekly insights
- Chat session history
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db.session import SessionLocal
from db.models.analytics_snapshot import AnalyticsSnapshot
from db.models.weekly_insight import WeeklyInsight
from db.models.chat_session import ChatSession
from db.models.channel import Channel
from db.models.video_snapshot import VideoSnapshot
from db.models.video import Video

logger = logging.getLogger(__name__)


class PostgresMemoryStore:
    """
    Long-term memory store using PostgreSQL.

    Provides read and write access to persistent MCP data:
    - Channel analytics snapshots
    - Weekly growth insights
    - User chat session history
    """

    def __init__(self) -> None:
        """Initialize the PostgreSQL memory store."""
        logger.info("PostgresMemoryStore initialized")

    def _get_session(self) -> Session:
        """Create a new database session."""
        return SessionLocal()

    # -------------------------------------------------------------------------
    # READ METHODS
    # -------------------------------------------------------------------------

    def get_channel_by_id(self, channel_id: UUID) -> Optional[Channel]:
        """
        Retrieve a channel by its UUID.

        Args:
            channel_id: The UUID of the channel.

        Returns:
            The Channel object, or None if not found.
        """
        session = self._get_session()
        try:
            channel = (
                session.query(Channel)
                .filter(Channel.id == channel_id)
                .first()
            )
            return channel
        except Exception as e:
            logger.error(f"Error fetching channel by ID: {e}")
            raise
        finally:
            session.close()

    def get_channel_by_youtube_id(self, youtube_channel_id: str) -> Optional[Channel]:
        """
        Retrieve a channel by its YouTube channel ID.

        Args:
            youtube_channel_id: The YouTube channel ID string (e.g., UC0FDx7Q3QHg3ivswUBNrWsw).

        Returns:
            The Channel object, or None if not found.
        """
        session = self._get_session()
        try:
            channel = (
                session.query(Channel)
                .filter(Channel.youtube_channel_id == youtube_channel_id)
                .first()
            )
            return channel
        except Exception as e:
            logger.error(f"Error fetching channel by YouTube ID: {e}")
            raise
        finally:
            session.close()

    def get_latest_analytics_snapshot(
        self, channel_id: UUID
    ) -> Optional[AnalyticsSnapshot]:
        """
        Retrieve the most recent analytics snapshot for a channel.

        Args:
            channel_id: The UUID of the channel.

        Returns:
            The most recent AnalyticsSnapshot, or None if not found.
        """
        session = self._get_session()
        try:
            snapshot = (
                session.query(AnalyticsSnapshot)
                .filter(AnalyticsSnapshot.channel_id == channel_id)
                .order_by(desc(AnalyticsSnapshot.created_at))
                .first()
            )
            return snapshot
        except Exception as e:
            logger.error(f"Error fetching latest analytics snapshot: {e}")
            raise
        finally:
            session.close()

    def get_recent_weekly_insights(
        self, channel_id: UUID, limit: int = 3
    ) -> list[WeeklyInsight]:
        """
        Retrieve recent weekly insights for a channel.

        Args:
            channel_id: The UUID of the channel.
            limit: Maximum number of insights to return (default: 3).

        Returns:
            List of WeeklyInsight objects ordered by week_start descending.
        """
        session = self._get_session()
        try:
            insights = (
                session.query(WeeklyInsight)
                .filter(WeeklyInsight.channel_id == channel_id)
                .order_by(desc(WeeklyInsight.week_start))
                .limit(limit)
                .all()
            )
            return insights
        except Exception as e:
            logger.error(f"Error fetching recent weekly insights: {e}")
            raise
        finally:
            session.close()

    def get_recent_chat_sessions(
        self,
        user_id: UUID,
        channel_id: Optional[UUID] = None,
        limit: int = 5,
    ) -> list[ChatSession]:
        """
        Retrieve recent chat sessions for context.

        Args:
            user_id: The UUID of the user.
            channel_id: Optional channel UUID to filter by.
            limit: Maximum number of sessions to return (default: 5).

        Returns:
            List of ChatSession objects ordered by created_at descending.
        """
        session = self._get_session()
        try:
            query = session.query(ChatSession).filter(
                ChatSession.user_id == user_id
            )

            if channel_id is not None:
                query = query.filter(ChatSession.channel_id == channel_id)

            chat_sessions = (
                query.order_by(desc(ChatSession.created_at))
                .limit(limit)
                .all()
            )
            return chat_sessions
        except Exception as e:
            logger.error(f"Error fetching recent chat sessions: {e}")
            raise
        finally:
            session.close()

    def get_recent_video_snapshots(
        self, channel_id: UUID, limit: int = 50
    ) -> list[VideoSnapshot]:
        """
        Retrieve recent video snapshots for a channel.

        Used by the video resolver to find matching videos by title.

        Args:
            channel_id: The UUID of the channel.
            limit: Maximum number of snapshots to return (default: 50).

        Returns:
            List of VideoSnapshot objects ordered by snapshot_date descending.
        """
        session = self._get_session()
        try:
            snapshots = (
                session.query(VideoSnapshot)
                .filter(VideoSnapshot.channel_id == channel_id)
                .order_by(desc(VideoSnapshot.snapshot_date))
                .limit(limit)
                .all()
            )
            return snapshots
        except Exception as e:
            logger.error(f"Error fetching recent video snapshots: {e}")
            raise
        finally:
            session.close()

    def get_recent_videos(
        self, channel_id: UUID, limit: int = 100
    ) -> list[Video]:
        """
        Retrieve recent videos for a channel from the videos table.

        Used by the video resolver for fuzzy title matching.

        Args:
            channel_id: The UUID of the channel.
            limit: Maximum number of videos to return (default: 100).

        Returns:
            List of Video objects ordered by published_at descending.
        """
        session = self._get_session()
        try:
            videos = (
                session.query(Video)
                .filter(Video.channel_id == channel_id)
                .order_by(desc(Video.published_at))
                .limit(limit)
                .all()
            )
            return videos
        except Exception as e:
            logger.error(f"Error fetching recent videos: {e}")
            raise
        finally:
            session.close()

    # -------------------------------------------------------------------------
    # WRITE METHODS
    # -------------------------------------------------------------------------

    def save_analytics_snapshot(self, snapshot: AnalyticsSnapshot) -> None:
        """
        Persist an analytics snapshot to the database.

        Args:
            snapshot: The AnalyticsSnapshot object to save.

        Raises:
            Exception: If the database operation fails.
        """
        session = self._get_session()
        try:
            session.add(snapshot)
            session.commit()
            logger.debug(
                f"Saved analytics snapshot for channel {snapshot.channel_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving analytics snapshot: {e}")
            raise
        finally:
            session.close()

    def save_weekly_insight(self, insight: WeeklyInsight) -> None:
        """
        Persist a weekly insight to the database.

        Args:
            insight: The WeeklyInsight object to save.

        Raises:
            Exception: If the database operation fails.
        """
        session = self._get_session()
        try:
            session.add(insight)
            session.commit()
            logger.debug(
                f"Saved weekly insight for channel {insight.channel_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving weekly insight: {e}")
            raise
        finally:
            session.close()

    def save_chat_session(self, chat: ChatSession) -> None:
        """
        Persist a chat session to the database.

        Args:
            chat: The ChatSession object to save.

        Raises:
            Exception: If the database operation fails.
        """
        session = self._get_session()
        try:
            session.add(chat)
            session.commit()
            logger.debug(f"Saved chat session for user {chat.user_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving chat session: {e}")
            raise
        finally:
            session.close()

    def upsert_videos(
        self,
        channel_id: UUID,
        user_id: UUID,
        videos_data: list[dict[str, Any]],
    ) -> dict[str, int]:
        """
        Upsert video metadata into the videos table.

        Idempotent: inserts new videos and updates existing ones
        based on (channel_id, youtube_video_id) unique constraint.

        Args:
            channel_id: Channel UUID.
            user_id: User UUID.
            videos_data: List of dicts from YouTube API, each with:
                - video_id: YouTube video ID
                - title: Video title
                - published_at: ISO timestamp string
                - views: View count
                - likes: Like count
                - comments: Comment count

        Returns:
            Dict with {"inserted": N, "updated": M}
        """
        session = self._get_session()
        inserted = 0
        updated = 0

        try:
            for vdata in videos_data:
                yt_video_id = vdata.get("video_id", "")
                if not yt_video_id:
                    continue

                # Check if video already exists
                existing = (
                    session.query(Video)
                    .filter(
                        Video.channel_id == channel_id,
                        Video.youtube_video_id == yt_video_id,
                    )
                    .first()
                )

                # Parse published_at
                published_at = None
                raw_pub = vdata.get("published_at")
                if raw_pub:
                    try:
                        published_at = datetime.fromisoformat(
                            raw_pub.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        pass

                if existing:
                    # Update mutable fields
                    existing.title = vdata.get("title", existing.title)
                    existing.view_count = vdata.get("views", existing.view_count)
                    existing.like_count = vdata.get("likes", existing.like_count)
                    existing.comment_count = vdata.get("comments", existing.comment_count)
                    if published_at:
                        existing.published_at = published_at
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    # Insert new video
                    video = Video(
                        user_id=user_id,
                        channel_id=channel_id,
                        youtube_video_id=yt_video_id,
                        title=vdata.get("title", "Untitled"),
                        published_at=published_at,
                        view_count=vdata.get("views"),
                        like_count=vdata.get("likes"),
                        comment_count=vdata.get("comments"),
                    )
                    session.add(video)
                    inserted += 1

            session.commit()
            logger.info(
                f"[VideoUpsert] channel={channel_id}: "
                f"{inserted} inserted, {updated} updated"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Error upserting videos: {e}")
            raise
        finally:
            session.close()

        return {"inserted": inserted, "updated": updated}


# Global instance for convenience
postgres_store = PostgresMemoryStore()
