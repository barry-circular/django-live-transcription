#!/usr/bin/env python3
"""
Test script to demonstrate the new merging functionality.
This shows how new data is merged with existing data instead of overwriting.
"""

import json
from app import TranscriptionConsumer

def test_merge_functionality():
    """Test the merge functionality with sample data."""
    
    # Create a consumer instance
    consumer = TranscriptionConsumer()
    
    print("🧪 Testing Medical History Merging Functionality")
    print("=" * 60)
    
    # Test cases showing before/after merging
    test_cases = [
        {
            'section': 'mcas_allergic',
            'new_data': {'food_reactions': ['peanuts']},
            'description': 'Adding peanuts allergy to existing food reactions'
        },
        {
            'section': 'medications_supplements',
            'new_data': {'current_meds': [{"name": "Aspirin", "dose": "81 mg", "route": "oral", "frequency": "as needed", "indication": "headache relief"}]},
            'description': 'Adding aspirin to existing medications'
        },
        {
            'section': 'family_history',
            'new_data': {'other_chronic': ["Mother: diabetes"]},
            'description': 'Adding mother\'s diabetes to family history'
        },
        {
            'section': 'illness_timeline',
            'new_data': {'current_dominant_symptoms': ['headaches']},
            'description': 'Adding headaches to existing symptoms'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📝 Test {i}: {test_case['description']}")
        print("-" * 50)
        
        section_name = test_case['section']
        new_data = test_case['new_data']
        
        # Show existing data
        if section_name in consumer.patient_history:
            existing_data = consumer.patient_history[section_name]
            print(f"📋 Existing Data:")
            for key, value in new_data.items():
                if key in existing_data:
                    print(f"   {key}: {existing_data[key]}")
                else:
                    print(f"   {key}: (not present)")
        
        # Show new data to be added
        print(f"➕ New Data to Add:")
        for key, value in new_data.items():
            print(f"   {key}: {value}")
        
        # Perform merge
        merged_data = consumer.merge_section_data(section_name, new_data)
        
        # Show merged result
        print(f"🔄 Merged Result:")
        for key, value in new_data.items():
            if key in merged_data:
                print(f"   {key}: {merged_data[key]}")
        
        print("-" * 50)

if __name__ == "__main__":
    print("🎙️ Medical History Merge Test")
    print("This test demonstrates how new data is merged with existing data")
    print("")
    
    # Run the test
    test_merge_functionality()
    
    print("\n✅ Merge test completed!")
    print("\nKey Benefits:")
    print("• New items are added to existing lists")
    print("• Duplicates are automatically avoided")
    print("• Existing data is preserved")
    print("• Only new/changed data is sent over WebSocket")
