#!/usr/bin/env python3
"""
Test script to demonstrate medical history section updates.
This simulates the transcription processing without needing the full WebSocket setup.
"""

import asyncio
import json
from app import TranscriptionConsumer

async def test_medical_history_detection():
    """Test the medical history detection functionality."""
    
    # Create a mock consumer instance
    consumer = TranscriptionConsumer()
    
    # Test cases with different medical information
    test_transcripts = [
        "I've been having headaches lately",
        "My mother was diagnosed with diabetes",
        "I started taking aspirin for pain relief",
        "My ESR test came back at 15",
        "I'm walking about 7500 steps per day now",
        "I'm allergic to peanuts",
        "I had COVID again last month",
        "My sleep has improved significantly",
        "I'm taking vitamin D supplements",
        "I'm dizzy when I stand up quickly",
        # MCAS/Allergy specific test cases
        "I'm allergic to shellfish",
        "I get hives when I eat tree nuts",
        "I have facial flushing after eating dairy",
        "I experience tinnitus and ear ringing",
        "I have seasonal allergies to pollen",
        "I get a rash when I eat aged cheese",
        "I'm sensitive to histamine-rich foods",
        "I have dermatographia and skin reactions"
    ]
    
    print("🧪 Testing Medical History Section Updates")
    print("=" * 50)
    
    for i, transcript in enumerate(test_transcripts, 1):
        print(f"\n📝 Test {i}: '{transcript}'")
        print("-" * 30)
        
        # Test the detection function
        updates = await consumer.detect_medical_history_updates(transcript)
        
        if updates:
            for section_name, new_data, completeness in updates:
                print(f"🏥 Section: {section_name}")
                print(f"📊 Completeness: {completeness:.2f}")
                print(f"📋 New Data to Add: {json.dumps(new_data, indent=2)}")
                print(f"💡 Note: This will be merged with existing data, not overwrite it")
                
                # Simulate the WebSocket message that would be sent
                message = {
                    'type': 'section_update',
                    'section_name': section_name,
                    'new_data': new_data,
                    'completeness': completeness
                }
                print(f"📡 WebSocket Message: {json.dumps(message, indent=2)}")
        else:
            print("❌ No medical history updates detected")
        
        print("-" * 30)

if __name__ == "__main__":
    print("🎙️ Medical History Section Update Test")
    print("This test demonstrates how transcription text triggers section updates")
    print("")
    
    # Run the test
    asyncio.run(test_medical_history_detection())
    
    print("\n✅ Test completed!")
    print("\nTo see this in action:")
    print("1. Run: python app.py")
    print("2. Open: http://localhost:8080")
    print("3. Start transcription and say phrases like:")
    print("   - 'I have headaches'")
    print("   - 'My mother has diabetes'")
    print("   - 'I take aspirin'")
    print("   - 'I walk 8000 steps per day'")
    print("   - 'I'm allergic to peanuts'")
    print("   - 'I'm allergic to shellfish'")
    print("   - 'I get hives from tree nuts'")
    print("   - 'I have facial flushing'")
    print("   - 'I experience tinnitus'")
    print("   - 'I have seasonal allergies'")
