"""
Simple test for Train Data Function
"""

import pytest
from unittest.mock import Mock

def test_station_lookup():
    """Test station lookup logic"""
    # Import after pytest is installed
    from function_app import get_or_create_station
    
    # Mock cursor that returns station ID
    mock_cursor = Mock()
    mock_cursor.fetchone.return_value = (123,)
    
    # Test function
    result = get_or_create_station(mock_cursor, "Brussels-Central")
    
    # Verify result
    assert result == 123
    print("✅ Test passed!")

# Run with: pytest tests/test_simple.py -v