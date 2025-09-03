"""
Time utilities for Discord snowflake parsing and UTC handling.
Source: spec.md - Entry T0 from Discord snowflake (UTC)
"""

from datetime import datetime, timezone
from typing import Union


# Discord epoch: 2015-01-01 00:00:00 UTC
DISCORD_EPOCH = 1420070400000


def snowflake_to_datetime(snowflake: Union[str, int]) -> datetime:
    """
    Convert Discord snowflake ID to UTC datetime.
    
    Args:
        snowflake: Discord message ID (snowflake)
        
    Returns:
        UTC datetime when the message was created (T0)
    """
    snowflake_int = int(snowflake)
    timestamp_ms = (snowflake_int >> 22) + DISCORD_EPOCH
    return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)


def datetime_to_epoch_ms(dt: datetime) -> int:
    """Convert datetime to epoch milliseconds for API compatibility."""
    return int(dt.timestamp() * 1000)


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC timezone-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_entry_timestamp(message_id: str) -> datetime:
    """
    Get T0 entry timestamp from Discord message ID.
    This is the canonical entry time for all calculations.
    
    Args:
        message_id: Discord snowflake ID
        
    Returns:
        T0 timestamp in UTC
    """
    return snowflake_to_datetime(message_id)
