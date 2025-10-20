#!/usr/bin/env python3
"""
Script to scrape actual video timestamps from Granicus pages and map them to meta_ids.
This will fix the timestamp calculation issue.
"""

import json
import re
import subprocess
import os

def scrape_video_timestamps(meeting_id):
    """Scrape video timestamps from Granicus page."""
    url = f"https://torrance.granicus.com/player/clip/{meeting_id}"
    
    try:
        result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, check=True)
        html_content = result.stdout
        
        # Extract time attributes
        time_pattern = r'time="(\d+)"'
        timestamps = re.findall(time_pattern, html_content)
        
        # Convert to integers and sort
        timestamps = sorted([int(t) for t in timestamps])
        
        print(f"  Found {len(timestamps)} timestamps: {timestamps[:10]}...")
        return timestamps
        
    except subprocess.CalledProcessError as e:
        print(f"  Error scraping {url}: {e}")
        return []

def scrape_meta_id_timestamps(meeting_id):
    """Scrape meta_id to timestamp mapping from Granicus page."""
    url = f"https://torrance.granicus.com/player/clip/{meeting_id}"
    
    try:
        result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, check=True)
        html_content = result.stdout
        
        # Look for data-id and time patterns together
        # Pattern: data-id="123" time="456" (can be on separate lines)
        meta_time_pattern = r'time="(\d+)".*?data-id="(\d+)"'
        matches = re.findall(meta_time_pattern, html_content, re.DOTALL)
        
        meta_time_map = {}
        for time_str, meta_id in matches:
            meta_time_map[meta_id] = int(time_str)
        
        print(f"  Found {len(meta_time_map)} meta_id->time mappings")
        if meta_time_map:
            print(f"    Sample: {dict(list(meta_time_map.items())[:3])}")
        return meta_time_map
        
    except subprocess.CalledProcessError as e:
        print(f"  Error scraping {url}: {e}")
        return {}

def update_vote_timestamps():
    """Update vote data with actual video timestamps."""
    
    # Load current data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    votes = data.get('votes', [])
    meetings = data.get('meetings', {})
    
    print(f"🔍 Processing {len(votes)} votes across {len(meetings)} meetings...")
    
    # Get unique meeting IDs
    meeting_ids = set(vote.get('meeting_id') for vote in votes)
    
    # Scrape timestamps for each meeting
    meeting_timestamps = {}
    meeting_meta_timestamps = {}
    
    for meeting_id in meeting_ids:
        print(f"\n📋 Scraping meeting {meeting_id}...")
        
        # Get all timestamps
        timestamps = scrape_video_timestamps(meeting_id)
        meeting_timestamps[meeting_id] = timestamps
        
        # Get meta_id to timestamp mapping
        meta_timestamps = scrape_meta_id_timestamps(meeting_id)
        meeting_meta_timestamps[meeting_id] = meta_timestamps
    
    # Update votes with actual timestamps
    updated_votes = 0
    
    for vote in votes:
        meeting_id = vote.get('meeting_id')
        meta_id = vote.get('meta_id')
        
        if meeting_id and meta_id:
            # Try to get timestamp from meta_id mapping
            meta_timestamps = meeting_meta_timestamps.get(meeting_id, {})
            if str(meta_id) in meta_timestamps:
                actual_timestamp = meta_timestamps[str(meta_id)]
                vote['video_timestamp'] = actual_timestamp
                vote['timestamp_estimated'] = False  # Mark as actual timestamp
                updated_votes += 1
                print(f"✅ Vote: meta_id {meta_id} -> {actual_timestamp}s")
            else:
                # Fallback: estimate from frame number (but mark as estimated)
                frame_number = vote.get('frame_number', 0)
                estimated_seconds = frame_number / 30
                vote['video_timestamp'] = int(estimated_seconds)
                vote['timestamp_estimated'] = True
                print(f"⚠️  Vote: meta_id {meta_id} -> estimated {int(estimated_seconds)}s")
    
    print(f"\n📊 Summary:")
    print(f"  Total votes: {len(votes)}")
    print(f"  Updated with actual timestamps: {updated_votes}")
    print(f"  Estimated timestamps: {len(votes) - updated_votes}")
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n💾 Updated data saved")
    
    # Save timestamp mapping for reference
    timestamp_data = {
        'meeting_timestamps': meeting_timestamps,
        'meeting_meta_timestamps': meeting_meta_timestamps,
        'updated_at': '2025-01-20'
    }
    
    with open('data/video_timestamps.json', 'w') as f:
        json.dump(timestamp_data, f, indent=2)
    
    print(f"💾 Timestamp mapping saved to data/video_timestamps.json")

if __name__ == "__main__":
    update_vote_timestamps()
