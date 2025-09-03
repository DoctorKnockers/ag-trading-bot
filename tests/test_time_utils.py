"""Tests for time utility functions."""

import pytest
from datetime import datetime, timezone, timedelta

from utils.time_utils import snowflake_to_datetime, datetime_to_epoch_ms, get_entry_timestamp


class TestTimeUtils:
    """Test time utility functions."""
    
    def test_snowflake_to_datetime(self):
        """Test Discord snowflake conversion."""
        # Test with a known recent snowflake
        snowflake = "1320000000000000000"  # ~2024-12-21
        
        dt = snowflake_to_datetime(snowflake)
        
        # Should be in 2024
        assert dt.year == 2024
        assert dt.month == 12
        assert dt.tzinfo == timezone.utc
    
    def test_snowflake_to_datetime_int(self):
        """Test with integer snowflake."""
        snowflake = 1320000000000000000
        dt = snowflake_to_datetime(snowflake)
        
        assert dt.year == 2024
        assert dt.tzinfo == timezone.utc
    
    def test_datetime_to_epoch_ms(self):
        """Test datetime to epoch milliseconds conversion."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        epoch_ms = datetime_to_epoch_ms(dt)
        
        assert epoch_ms == 1704067200000
    
    def test_get_entry_timestamp(self):
        """Test T0 entry timestamp extraction."""
        message_id = "1320000000000000000"
        t0 = get_entry_timestamp(message_id)
        
        assert isinstance(t0, datetime)
        assert t0.tzinfo == timezone.utc
        assert t0.year == 2024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
