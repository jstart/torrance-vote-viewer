#!/usr/bin/env python3
"""
Check frame availability and provide status report
"""

import json
import os

def check_frame_availability():
    """Check which frames are available and which are missing"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("🔍 Frame Availability Report")
    print("=" * 50)
    
    # Check frame availability
    available_frames = 0
    missing_frames = 0
    meetings_with_frames = set()
    meetings_without_frames = set()
    
    for vote in data.get('votes', []):
        if vote.get('frame_path'):
            meeting_id = vote.get('meeting_id')
            if os.path.exists(vote['frame_path']):
                available_frames += 1
                meetings_with_frames.add(meeting_id)
            else:
                missing_frames += 1
                meetings_without_frames.add(meeting_id)
    
    print(f"📊 Overall Statistics:")
    print(f"   - Available frames: {available_frames}")
    print(f"   - Missing frames: {missing_frames}")
    print(f"   - Total votes with frame paths: {available_frames + missing_frames}")
    
    print(f"\n✅ Meetings with available frames ({len(meetings_with_frames)}):")
    for meeting_id in sorted(meetings_with_frames):
        print(f"   - Meeting {meeting_id}")
    
    print(f"\n❌ Meetings missing frames ({len(meetings_without_frames)}):")
    for meeting_id in sorted(meetings_without_frames):
        print(f"   - Meeting {meeting_id}")
    
    # Check by year
    print(f"\n📅 By Year:")
    for meeting_id in sorted(meetings_with_frames | meetings_without_frames):
        if meeting_id and meeting_id.startswith('14'):
            year = '2024'
        elif meeting_id and meeting_id.startswith('15'):
            year = '2025'
        else:
            year = 'Unknown'
        
        status = "✅ Available" if meeting_id in meetings_with_frames else "❌ Missing"
        print(f"   - Meeting {meeting_id} ({year}): {status}")
    
    # Check specific missing frame
    print(f"\n🔍 Specific Frame Check:")
    missing_frame = "2024_meetings_data/votable_frames_14319/chapter_05_frames_003505.jpg"
    if os.path.exists(missing_frame):
        print(f"   ✅ {missing_frame} - EXISTS")
    else:
        print(f"   ❌ {missing_frame} - MISSING")
        print(f"   📁 Directory exists: {os.path.exists(os.path.dirname(missing_frame))}")
    
    print(f"\n💡 Recommendations:")
    if missing_frames > 0:
        print(f"   1. 2024 meeting frames need to be processed/added")
        print(f"   2. Check if 2024 frames exist in other directories")
        print(f"   3. Consider reprocessing 2024 meetings to extract frames")
        print(f"   4. Update frame_available flags in data")
    else:
        print(f"   All frames are available!")

if __name__ == "__main__":
    check_frame_availability()
