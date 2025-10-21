#!/usr/bin/env python3
"""
Sample Usage Scripts for Bulletproof Import
===========================================

This file contains example usage patterns for the bulletproof import script.
"""

import os
import json
from bulletproof_import import BulletproofImporter, ImportConfig

def create_sample_data():
    """Create sample data for testing"""
    sample_data = {
        "votes": [
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
                    "ASAM SHEIKH": "YES"
                }
            },
            {
                "id": "14520_2",
                "meeting_id": "14520",
                "agenda_item": "2. Pledge of Allegiance",
                "frame_number": 2,
                "individual_votes": {
                    "GEORGE CHEN": "YES",
                    "MIKE GERSON": "YES",
                    "JON KAJI": "YES",
                    "SHARON KALANI": "YES",
                    "ASAM SHEIKH": "YES"
                }
            },
            {
                "id": "14520_3",
                "meeting_id": "14520",
                "agenda_item": "3. Public Comment",
                "frame_number": 3,
                "individual_votes": {
                    "GEORGE CHEN": "YES",
                    "MIKE GERSON": "YES",
                    "JON KAJI": "YES",
                    "SHARON KALANI": "YES",
                    "ASAM SHEIKH": "YES"
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

    with open('sample_new_meeting.json', 'w') as f:
        json.dump(sample_data, f, indent=2)

    print("Sample data created: sample_new_meeting.json")

def run_dry_run_import():
    """Run import in dry-run mode"""
    config = ImportConfig(
        input_file='sample_new_meeting.json',
        dry_run=True,
        verbose=True
    )

    importer = BulletproofImporter(config)
    importer.run_import()

def run_full_import():
    """Run full import with all features"""
    config = ImportConfig(
        input_file='sample_new_meeting.json',
        dry_run=False,
        verbose=True,
        gemini_api_key=os.getenv('GEMINI_API_KEY')  # Set this environment variable
    )

    importer = BulletproofImporter(config)
    importer.run_import()

def run_batch_import():
    """Run import on multiple files"""
    input_files = [
        'data/new_meeting_1.json',
        'data/new_meeting_2.json',
        'data/new_meeting_3.json'
    ]

    for input_file in input_files:
        if os.path.exists(input_file):
            print(f"Processing {input_file}...")
            config = ImportConfig(
                input_file=input_file,
                dry_run=False,
                verbose=False
            )

            importer = BulletproofImporter(config)
            importer.run_import()
        else:
            print(f"File not found: {input_file}")

def validate_existing_data():
    """Validate existing consolidated data"""
    config = ImportConfig(
        input_file='data/torrance_votes_smart_consolidated.json',
        dry_run=True,
        verbose=True
    )

    importer = BulletproofImporter(config)

    # Load and validate existing data
    issues = importer.validate_data_integrity(importer.existing_data)

    if issues:
        print(f"Found {len(issues)} validation issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("No validation issues found!")

if __name__ == '__main__':
    print("Bulletproof Import - Sample Usage")
    print("==================================")
    print()
    print("Available functions:")
    print("1. create_sample_data() - Create sample data for testing")
    print("2. run_dry_run_import() - Run import in dry-run mode")
    print("3. run_full_import() - Run full import with all features")
    print("4. run_batch_import() - Run import on multiple files")
    print("5. validate_existing_data() - Validate existing data")
    print()

    # Uncomment the function you want to run:
    # create_sample_data()
    # run_dry_run_import()
    # run_full_import()
    # run_batch_import()
    # validate_existing_data()
