#!/usr/bin/env python3
"""
Test script to verify the notification data flow.
This tests that we're sending the correct data for notifications.
"""

import json
from app import TranscriptionConsumer

def test_notification_data_flow():
    """Test that the notification data flow is correct."""
    
    # Create a consumer instance
    consumer = TranscriptionConsumer()
    
    print("🧪 Testing Notification Data Flow")
    print("=" * 50)
    
    # Test case: Adding peanuts allergy
    test_transcript = "I'm allergic to peanuts"
    
    print(f"📝 Test transcript: '{test_transcript}'")
    print("-" * 30)
    
    # Get the updates
    import asyncio
    updates = asyncio.run(consumer.detect_medical_history_updates(test_transcript))
    
    for section_name, new_data, completeness in updates:
        print(f"🏥 Section: {section_name}")
        print(f"📊 Completeness: {completeness:.2f}")
        print(f"📋 Original New Data: {json.dumps(new_data, indent=2)}")
        
        # Simulate the merge
        merged_data = consumer.merge_section_data(section_name, new_data)
        print(f"🔄 Merged Data: {json.dumps(merged_data, indent=2)}")
        
        # Simulate the WebSocket message
        message = {
            'type': 'section_update',
            'section_name': section_name,
            'new_data': merged_data,  # For section display
            'original_new_data': new_data,  # For notification
            'completeness': completeness
        }
        
        print(f"📡 WebSocket Message Structure:")
        print(f"   - new_data (for display): {len(str(merged_data))} chars")
        print(f"   - original_new_data (for notification): {len(str(new_data))} chars")
        
        # Show what the notification would display
        print(f"🔔 Notification would show:")
        for key, value in new_data.items():
            if isinstance(value, list):
                print(f"   Added {key}: {value}")
            else:
                print(f"   Updated {key}: {value}")
        
        print("-" * 30)

if __name__ == "__main__":
    print("🎙️ Notification Data Flow Test")
    print("This test verifies that notifications show only new data")
    print("")
    
    # Run the test
    test_notification_data_flow()
    
    print("\n✅ Test completed!")
    print("\nExpected behavior:")
    print("• new_data: Full merged section data (for display)")
    print("• original_new_data: Only the new items (for notification)")
    print("• Notification: Shows only what was added/updated")
