#!/usr/bin/env python3
"""
Test Script for Bulletproof Import System
=========================================

This script tests the bulletproof import system with sample data.
"""

import json
import os
import sys
from datetime import datetime

def create_test_data():
    """Create comprehensive test data"""
    test_data = {
        "votes": [
            # Test case 1: Normal vote
            {
                "id": "14520_1",
                "meeting_id": "14520",
                "agenda_item": "1. Call to Order",
                "frame_number": 1,
                "individual_votes": {
                    "GEORGE CHEN": "YES",
                    "MIKE GERSON": "YES",
                    "JON KAJI": "YES",
                    "SHARON KALANI": "YES",
                    "ASAM SHAIKH": "YES"
                }
            },
            # Test case 2: Duplicate vote (should be consolidated)
            {
                "id": "14520_1_dup",
                "meeting_id": "14520",
                "agenda_item": "1. Call to Order",
                "frame_number": 2,
                "individual_votes": {
                    "GEORGE CHEN": "YES",
                    "MIKE GERSON": "YES",
                    "JON KAJI": "YES",
                    "SHARON KALANI": "YES",
                    "ASAM SHAIKH": "YES"
                }
            },
            # Test case 3: Vote with existing meta_id
            {
                "id": "14520_2",
                "meeting_id": "14520",
                "agenda_item": "2. Pledge of Allegiance",
                "frame_number": 3,
                "individual_votes": {
                    "GEORGE CHEN": "YES",
                    "MIKE GERSON": "YES",
                    "JON KAJI": "YES",
                    "SHARON KALANI": "YES",
                    "ASAM SHAIKH": "YES"
                },
                "meta_id": "12345",
                "video_timestamp": 120,
                "timestamp_estimated": False
            },
            # Test case 4: Failed vote
            {
                "id": "14520_3",
                "meeting_id": "14520",
                "agenda_item": "3. Budget Approval",
                "frame_number": 4,
                "individual_votes": {
                    "GEORGE CHEN": "NO",
                    "MIKE GERSON": "NO",
                    "JON KAJI": "YES",
                    "SHARON KALANI": "YES",
                    "ASAM SHAIKH": "NO"
                }
            },
            # Test case 5: Vote with abstentions
            {
                "id": "14520_4",
                "meeting_id": "14520",
                "agenda_item": "4. Zoning Change",
                "frame_number": 5,
                "individual_votes": {
                    "GEORGE CHEN": "YES",
                    "MIKE GERSON": "ABSTAIN",
                    "JON KAJI": "YES",
                    "SHARON KALANI": "ABSTAIN",
                    "ASAM SHAIKH": "YES"
                }
            }
        ],
        "meetings": {
            "14520": {
                "id": "14520",
                "title": "City Council Meeting",
                "date": "2025-01-15",
                "time": "19:00",
                "video_url": "https://torrance.granicus.com/player/clip/14520",
                "agenda_url": "https://torrance.granicus.com/ViewPublisher.php?view_id=2&clip_id=14520"
            }
        }
    }

    with open('test_meeting_data.json', 'w') as f:
        json.dump(test_data, f, indent=2)

    print("✅ Test data created: test_meeting_data.json")
    return test_data

def test_deduplication():
    """Test deduplication logic"""
    print("\n🧪 Testing Deduplication Logic...")

    from bulletproof_import import BulletproofImporter, ImportConfig

    # Create test data
    test_data = create_test_data()

    # Create importer
    config = ImportConfig(
        input_file='test_meeting_data.json',
        dry_run=True,
        verbose=True
    )

    importer = BulletproofImporter(config)

    # Test deduplication
    votes = test_data['votes']
    consolidated_votes = importer.deduplicate_votes(votes)

    print(f"📊 Original votes: {len(votes)}")
    print(f"📊 Consolidated votes: {len(consolidated_votes)}")

    # Check for duplicate consolidation
    agenda_items = [vote.agenda_item for vote in consolidated_votes]
    unique_items = set(agenda_items)

    if len(agenda_items) == len(unique_items):
        print("✅ No duplicate agenda items found")
    else:
        print("❌ Duplicate agenda items still present")

    return consolidated_votes

def test_meta_id_mapping():
    """Test meta ID mapping (mock test)"""
    print("\n🧪 Testing Meta ID Mapping...")

    from bulletproof_import import BulletproofImporter, ImportConfig

    config = ImportConfig(
        input_file='test_meeting_data.json',
        dry_run=True,
        verbose=True
    )

    importer = BulletproofImporter(config)

    # Mock meta mappings
    mock_mappings = {
        "12345": {
            "video_timestamp": 120,
            "timestamp_estimated": False
        },
        "12346": {
            "video_timestamp": 180,
            "timestamp_estimated": False
        }
    }

    # Test mapping extraction
    test_html = '''
    <div class="chapter" time="120" data-id="12345">Chapter 1</div>
    <div class="chapter" time="180" data-id="12346">Chapter 2</div>
    '''

    mappings = importer.extract_meta_mappings(test_html)

    if mappings == mock_mappings:
        print("✅ Meta ID mapping extraction working correctly")
    else:
        print("❌ Meta ID mapping extraction failed")
        print(f"Expected: {mock_mappings}")
        print(f"Got: {mappings}")

    return mappings

def test_data_validation():
    """Test data validation"""
    print("\n🧪 Testing Data Validation...")

    from bulletproof_import import BulletproofImporter, ImportConfig

    config = ImportConfig(
        input_file='test_meeting_data.json',
        dry_run=True,
        verbose=True
    )

    importer = BulletproofImporter(config)

    # Test valid data
    test_data = create_test_data()
    issues = importer.validate_data_integrity(test_data)

    if not issues:
        print("✅ Valid data passed validation")
    else:
        print("❌ Valid data failed validation:")
        for issue in issues:
            print(f"  - {issue}")

    # Test invalid data
    invalid_data = {
        "votes": [
            {
                "id": "invalid_vote",
                # Missing required fields
            }
        ],
        "meetings": {
            "invalid_meeting": {
                # Missing required fields
            }
        }
    }

    issues = importer.validate_data_integrity(invalid_data)

    if issues:
        print("✅ Invalid data correctly flagged:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("❌ Invalid data should have been flagged")

def test_summary_generation():
    """Test summary generation (mock test)"""
    print("\n🧪 Testing Summary Generation...")

    from bulletproof_import import BulletproofImporter, ImportConfig

    config = ImportConfig(
        input_file='test_meeting_data.json',
        dry_run=True,
        verbose=True
    )

    importer = BulletproofImporter(config)

    # Create test votes
    from bulletproof_import import VoteData

    test_votes = [
        VoteData(
            meeting_id="14520",
            agenda_item="1. Call to Order",
            frame_number=1,
            individual_votes={"GEORGE CHEN": "YES", "MIKE GERSON": "YES"}
        ),
        VoteData(
            meeting_id="14520",
            agenda_item="2. Budget Approval",
            frame_number=2,
            individual_votes={"GEORGE CHEN": "NO", "MIKE GERSON": "YES"}
        )
    ]

    # Test summary generation (without API key)
    summary = importer.generate_meeting_summary("14520", test_votes)

    if summary:
        print("✅ Summary generation working (basic mode)")
        print(f"Summary: {summary.get('summary', 'No summary')}")
    else:
        print("⚠️ Summary generation skipped (no API key)")

def run_comprehensive_test():
    """Run all tests"""
    print("🚀 Running Comprehensive Import System Tests")
    print("=" * 50)

    try:
        # Test 1: Deduplication
        consolidated_votes = test_deduplication()

        # Test 2: Meta ID Mapping
        meta_mappings = test_meta_id_mapping()

        # Test 3: Data Validation
        test_data_validation()

        # Test 4: Summary Generation
        test_summary_generation()

        print("\n" + "=" * 50)
        print("🎉 All tests completed!")

        # Cleanup
        if os.path.exists('test_meeting_data.json'):
            os.remove('test_meeting_data.json')
            print("🧹 Cleaned up test files")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

def test_dry_run_import():
    """Test full dry-run import"""
    print("\n🧪 Testing Full Dry-Run Import...")

    from bulletproof_import import BulletproofImporter, ImportConfig

    # Create test data
    create_test_data()

    # Run import
    config = ImportConfig(
        input_file='test_meeting_data.json',
        dry_run=True,
        verbose=True
    )

    importer = BulletproofImporter(config)

    try:
        importer.run_import()
        print("✅ Dry-run import completed successfully")

        # Print statistics
        importer.print_stats()

    except Exception as e:
        print(f"❌ Dry-run import failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        if os.path.exists('test_meeting_data.json'):
            os.remove('test_meeting_data.json')

if __name__ == '__main__':
    print("Bulletproof Import System - Test Suite")
    print("======================================")

    if len(sys.argv) > 1:
        test_type = sys.argv[1]

        if test_type == 'dedup':
            test_deduplication()
        elif test_type == 'meta':
            test_meta_id_mapping()
        elif test_type == 'validation':
            test_data_validation()
        elif test_type == 'summary':
            test_summary_generation()
        elif test_type == 'dry-run':
            test_dry_run_import()
        else:
            print(f"Unknown test type: {test_type}")
    else:
        # Run all tests
        run_comprehensive_test()

        # Also run dry-run test
        test_dry_run_import()
