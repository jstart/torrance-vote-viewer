#!/usr/bin/env python3
"""
Update vote data to reflect which frames are actually available
"""

import json
import os

def update_frame_availability():
    """Update vote data to mark which frames are available"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("Updating frame availability...")
    
    available_frames = 0
    missing_frames = 0
    
    # Check each vote's frame
    for vote in data.get('votes', []):
        if vote.get('frame_path'):
            if os.path.exists(vote['frame_path']):
                vote['frame_available'] = True
                available_frames += 1
            else:
                vote['frame_available'] = False
                missing_frames += 1
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Updated frame availability:")
    print(f"   - Available frames: {available_frames}")
    print(f"   - Missing frames: {missing_frames}")
    print(f"   - Total votes: {len(data.get('votes', []))}")
    
    # Show which meetings have frames
    meetings_with_frames = set()
    meetings_without_frames = set()
    
    for vote in data.get('votes', []):
        meeting_id = vote.get('meeting_id')
        if vote.get('frame_available'):
            meetings_with_frames.add(meeting_id)
        else:
            meetings_without_frames.add(meeting_id)
    
    print(f"\n📁 Meetings with available frames: {len(meetings_with_frames)}")
    for meeting_id in sorted(meetings_with_frames):
        print(f"   - Meeting {meeting_id}")
    
    print(f"\n❌ Meetings missing frames: {len(meetings_without_frames)}")
    for meeting_id in sorted(meetings_without_frames):
        print(f"   - Meeting {meeting_id}")

if __name__ == "__main__":
    update_frame_availability()
