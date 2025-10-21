#!/usr/bin/env python3
"""
Copy frame images from source to the vote viewer directories
"""

import os
import shutil
import json
from pathlib import Path

def copy_frame_images():
    """Copy frame images from source directories to vote viewer"""
    
    # Source directories
    source_2025 = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data"
    
    # Load vote data to get frame paths
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("Copying frame images...")
    
    # Get all unique frame paths
    frame_paths = set()
    for vote in data.get('votes', []):
        if vote.get('frame_path'):
            frame_paths.add(vote['frame_path'])
    
    print(f"Found {len(frame_paths)} unique frame paths")
    
    copied_count = 0
    missing_count = 0
    
    for frame_path in frame_paths:
        # Determine source directory based on meeting ID
        meeting_id = None
        if '2025_meetings_data' in frame_path:
            meeting_id = frame_path.split('votable_frames_')[1].split('/')[0]
            source_dir = f"{source_2025}/votable_frames_{meeting_id}"
        elif '2024_meetings_data' in frame_path:
            meeting_id = frame_path.split('votable_frames_')[1].split('/')[0]
            # 2024 frames might not be available
            print(f"  ⚠️  2024 frames not available: {frame_path}")
            missing_count += 1
            continue
        
        if not meeting_id:
            continue
            
        # Extract filename from frame_path
        filename = os.path.basename(frame_path)
        
        # Source file path
        source_file = os.path.join(source_dir, filename)
        
        # Destination file path
        dest_file = frame_path
        
        # Create destination directory if it doesn't exist
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        
        # Copy file if it exists
        if os.path.exists(source_file):
            try:
                shutil.copy2(source_file, dest_file)
                copied_count += 1
                print(f"  ✅ Copied: {filename}")
            except Exception as e:
                print(f"  ❌ Error copying {filename}: {e}")
                missing_count += 1
        else:
            print(f"  ❌ Missing: {source_file}")
            missing_count += 1
    
    print(f"\n📊 Copy Results:")
    print(f"   - Copied: {copied_count} frames")
    print(f"   - Missing: {missing_count} frames")
    print(f"   - Total: {len(frame_paths)} frames")
    
    # Check what meetings we have frames for
    meetings_with_frames = set()
    for frame_path in frame_paths:
        if os.path.exists(frame_path):
            meeting_id = frame_path.split('votable_frames_')[1].split('/')[0]
            meetings_with_frames.add(meeting_id)
    
    print(f"\n📁 Meetings with frames: {len(meetings_with_frames)}")
    for meeting_id in sorted(meetings_with_frames):
        print(f"   - Meeting {meeting_id}")

if __name__ == "__main__":
    copy_frame_images()
