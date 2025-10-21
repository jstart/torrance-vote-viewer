#!/usr/bin/env python3
"""
Update meeting metadata to reflect actual vote counts after deduplication
"""

import json
import re

def update_meeting_metadata():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print(f"Updating meeting metadata for {len(data['meetings'])} meetings...")
    
    # Calculate actual vote counts for each meeting
    meeting_vote_counts = {}
    meeting_passed_counts = {}
    meeting_failed_counts = {}
    
    for vote in data['votes']:
        meeting_id = vote.get('meeting_id')
        if not meeting_id:
            continue
            
        # Count total votes
        if meeting_id not in meeting_vote_counts:
            meeting_vote_counts[meeting_id] = 0
        meeting_vote_counts[meeting_id] += 1
        
        # Count passed/failed votes
        result = vote.get('result', '').lower()
        if 'pass' in result:
            if meeting_id not in meeting_passed_counts:
                meeting_passed_counts[meeting_id] = 0
            meeting_passed_counts[meeting_id] += 1
        elif 'fail' in result:
            if meeting_id not in meeting_failed_counts:
                meeting_failed_counts[meeting_id] = 0
            meeting_failed_counts[meeting_id] += 1
    
    # Update meeting metadata
    meetings_updated = 0
    for meeting_id, meeting_data in data['meetings'].items():
        old_total = meeting_data.get('total_votes', 0)
        new_total = meeting_vote_counts.get(meeting_id, 0)
        new_passed = meeting_passed_counts.get(meeting_id, 0)
        new_failed = meeting_failed_counts.get(meeting_id, 0)
        
        if old_total != new_total:
            meeting_data['total_votes'] = new_total
            meeting_data['passed_votes'] = new_passed
            meeting_data['failed_votes'] = new_failed
            meetings_updated += 1
            
            print(f"Meeting {meeting_id}: {old_total} → {new_total} votes ({new_passed} passed, {new_failed} failed)")
    
    print(f"\n✅ Updated {meetings_updated} meetings with correct vote counts")
    
    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Meeting metadata updated!")

if __name__ == "__main__":
    update_meeting_metadata()
