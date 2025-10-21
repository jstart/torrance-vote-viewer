#!/usr/bin/env python3
"""
Extract timestamps from 2024 meeting frame paths and update vote data
"""

import json
import re
import os

def extract_timestamp_from_frame_path(frame_path):
    """Extract timestamp from frame path like chapter_08_frames_004259.jpg"""
    if not frame_path:
        return None
    
    # Look for pattern like chapter_XX_frames_XXXXXX.jpg
    match = re.search(r'chapter_\d+_frames_(\d+)\.jpg', frame_path)
    if match:
        # The number in the filename represents the timestamp in seconds
        timestamp_seconds = int(match.group(1))
        return timestamp_seconds
    
    # Look for pattern like frame_XXXXXX.jpg
    match = re.search(r'frame_(\d+)\.jpg', frame_path)
    if match:
        timestamp_seconds = int(match.group(1))
        return timestamp_seconds
    
    return None

def update_2024_timestamps():
    """Update video timestamps for 2024 meetings based on frame paths"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("🔄 Updating 2024 meeting timestamps...")
    
    updated_count = 0
    
    for vote in data.get('votes', []):
        # Only process 2024 meetings
        if (vote.get('meeting_id') and 
            vote.get('meeting_id').startswith('14') and 
            int(vote.get('meeting_id', '0')) < 14400):
            
            frame_path = vote.get('frame_path')
            if frame_path and not vote.get('video_timestamp'):
                # Extract timestamp from frame path
                timestamp = extract_timestamp_from_frame_path(frame_path)
                if timestamp:
                    vote['video_timestamp'] = timestamp
                    vote['timestamp_estimated'] = True  # Mark as estimated since we derived it
                    updated_count += 1
                    print(f"  ✅ Meeting {vote.get('meeting_id')} - Frame {vote.get('frame_number')}: {timestamp}s")
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n📊 Update Results:")
    print(f"   - Updated timestamps: {updated_count}")
    print(f"   - 2024 meetings now have video timestamps for deeplinking")

if __name__ == "__main__":
    update_2024_timestamps()
