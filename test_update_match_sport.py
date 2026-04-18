#!/usr/bin/env python3
"""
Test script to verify the sport field was added to UpdateMatchRequest.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_update_match_schema():
    """Test that UpdateMatchRequest now includes sport field."""
    print("Testing UpdateMatchRequest schema with sport field...")

    try:
        from app.schemas.match import UpdateMatchRequest
        from app.models.enums import SportType
        
        # Test 1: Create UpdateMatchRequest with sport field
        update_request = UpdateMatchRequest(
            title="Updated Basketball Match",
            sport=SportType.BASKETBALL,
            skill_level="Intermediate"
        )
        
        print(f"✅ UpdateMatchRequest created successfully")
        print(f"   - Title: {update_request.title}")
        print(f"   - Sport: {update_request.sport}")
        
        # Test 2: Verify sport field is optional (can be None)
        update_request_partial = UpdateMatchRequest(
            title="Partial Update"
        )
        print(f"✅ UpdateMatchRequest with partial fields (sport=None)")
        print(f"   - Title: {update_request_partial.title}")
        print(f"   - Sport: {update_request_partial.sport}")
        
        # Test 3: Verify all sport types work
        for sport in SportType:
            update_with_sport = UpdateMatchRequest(sport=sport)
            assert update_with_sport.sport == sport
        print(f"✅ All SportType values work: {[s.value for s in SportType]}")
        
        return True
    except Exception as e:
        print(f"❌ Schema test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_imports():
    """Test that all match schema imports work."""
    print("\nTesting match schema imports...")

    try:
        from app.schemas.match import (
            CreateMatchRequest,
            UpdateMatchRequest,
            MatchDetailResponse,
            MatchSummaryResponse,
        )
        from app.models.enums import SportType, SkillLevel
        
        print("✅ All match schemas import successfully")
        
        # Verify CreateMatchRequest has sport (required)
        assert hasattr(CreateMatchRequest, 'model_fields')
        assert 'sport' in CreateMatchRequest.model_fields
        print("✅ CreateMatchRequest has sport field")
        
        # Verify UpdateMatchRequest has sport (optional)
        assert 'sport' in UpdateMatchRequest.model_fields
        print("✅ UpdateMatchRequest has sport field")
        
        return True
    except Exception as e:
        print(f"❌ Import test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("🧪 Testing Sport Field in Update Match API")
    print("=" * 60)

    success = True
    success &= test_imports()
    success &= test_update_match_schema()

    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests passed! Sport field added successfully.")
        print("\nUpdate Match API now supports:")
        print("  - title (optional)")
        print("  - description (optional)")
        print("  - sport (optional) ← NEW!")
        print("  - facility_address (optional)")
        print("  - location (optional)")
        print("  - location_name (optional)")
        print("  - latitude (optional)")
        print("  - longitude (optional)")
        print("  - scheduled_at (optional)")
        print("  - duration_minutes (optional)")
        print("  - max_players (optional)")
        print("  - skill_level (optional)")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
