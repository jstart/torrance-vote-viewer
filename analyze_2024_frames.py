#!/usr/bin/env python3
"""
Create a plan to process 2024 meeting frames
"""

import json
import os

def analyze_2024_frame_requirements():
    """Analyze what 2024 frames are needed and create a processing plan"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("🔍 2024 Frame Processing Analysis")
    print("=" * 50)
    
    # Find all 2024 votes that need frames
    votes_2024 = [vote for vote in data.get('votes', []) 
                  if vote.get('meeting_id') and vote.get('meeting_id').startswith('14') 
                  and int(vote.get('meeting_id', '0')) < 14400]
    
    print(f"📊 2024 Votes Analysis:")
    print(f"   - Total 2024 votes: {len(votes_2024)}")
    
    # Group by meeting
    meetings_2024 = {}
    for vote in votes_2024:
        meeting_id = vote.get('meeting_id')
        if meeting_id not in meetings_2024:
            meetings_2024[meeting_id] = []
        meetings_2024[meeting_id].append(vote)
    
    print(f"   - 2024 meetings with votes: {len(meetings_2024)}")
    
    # Show frame requirements by meeting
    print(f"\n📋 Frame Requirements by Meeting:")
    for meeting_id in sorted(meetings_2024.keys()):
        votes = meetings_2024[meeting_id]
        frame_paths = [vote.get('frame_path') for vote in votes if vote.get('frame_path')]
        unique_frames = set(frame_paths)
        
        print(f"   - Meeting {meeting_id}: {len(votes)} votes, {len(unique_frames)} unique frames")
        
        # Show sample frame paths
        if unique_frames:
            sample_frames = list(unique_frames)[:3]
            for frame_path in sample_frames:
                print(f"     • {frame_path}")
            if len(unique_frames) > 3:
                print(f"     • ... and {len(unique_frames) - 3} more")
    
    print(f"\n💡 Processing Options:")
    print(f"   1. Extract frames from original 2024 meeting videos")
    print(f"   2. Use existing frame extraction tools from the project")
    print(f"   3. Process frames in batches by meeting")
    print(f"   4. Update frame_available flags after processing")
    
    print(f"\n🛠️  Recommended Next Steps:")
    print(f"   1. Check if 2024 meeting videos are available")
    print(f"   2. Use existing frame extraction scripts")
    print(f"   3. Process one meeting at a time (start with 14319)")
    print(f"   4. Update the vote data with processed frames")
    
    # Create a processing script template
    script_content = '''#!/usr/bin/env python3
"""
Process 2024 meeting frames - Template
"""

import os
import subprocess
from pathlib import Path

def process_2024_meeting_frames():
    """Process frames for 2024 meetings"""
    
    # 2024 meetings that need frames
    meetings_2024 = [
        "14243", "14262", "14273", "14286", "14305", 
        "14312", "14314", "14319", "14350"
    ]
    
    for meeting_id in meetings_2024:
        print(f"Processing meeting {meeting_id}...")
        
        # Create output directory
        output_dir = f"2024_meetings_data/votable_frames_{meeting_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        # TODO: Add frame extraction logic here
        # This would typically involve:
        # 1. Finding the meeting video
        # 2. Extracting frames at specific timestamps
        # 3. Saving frames with correct naming convention
        
        print(f"  ✅ Created directory: {output_dir}")

if __name__ == "__main__":
    process_2024_meeting_frames()
'''
    
    with open('process_2024_frames_template.py', 'w') as f:
        f.write(script_content)
    
    print(f"\n📝 Created processing template: process_2024_frames_template.py")

if __name__ == "__main__":
    analyze_2024_frame_requirements()
