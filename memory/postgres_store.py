"""
PostgreSQL-based long-term memory store.

Provides persistent storage for:
- Analytics snapshots
- Weekly insights
- Chat session history
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db.session import SessionLocal
from db.models.analytics_snapshot import AnalyticsSnapshot
from db.models.weekly_insight import WeeklyInsight
from db.models.chat_session import ChatSession
from db.models.channel import Channel

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


# Global instance for convenience
postgres_store = PostgresMemoryStore()
