#!/usr/bin/env python3
"""
Create frame images directory structure for vote frames
"""

import os
import json
from pathlib import Path

def create_frame_directories():
    """Create directory structure for vote frame images"""
    
    # Load vote data to get all unique frame paths
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("Creating frame images directory structure...")
    
    # Get all unique frame paths
    frame_paths = set()
    for vote in data.get('votes', []):
        if vote.get('frame_path'):
            frame_paths.add(vote['frame_path'])
    
    print(f"Found {len(frame_paths)} unique frame paths")
    
    # Create directories for each meeting
    created_dirs = set()
    
    for frame_path in frame_paths:
        # Extract directory path
        dir_path = os.path.dirname(frame_path)
        
        if dir_path not in created_dirs:
            os.makedirs(dir_path, exist_ok=True)
            created_dirs.add(dir_path)
            print(f"  Created directory: {dir_path}")
    
    # Create frame_images directory and README
    os.makedirs('frame_images', exist_ok=True)
    
    readme_content = """# Vote Frame Images

This directory contains the actual frame images from city council meetings that show the vote results.

## Directory Structure

- `2024_meetings_data/votable_frames_XXXXX/` - 2024 meeting frames
- `2025_meetings_data/votable_frames_XXXXX/` - 2025 meeting frames

## File Naming Convention

- `chapter_XX_frames_XXXXXX.jpg` - Chapter frames with timestamp
- `frame_XXXXXX.jpg` - Direct frame numbers

## Adding Frame Images

To add frame images:

1. Place the frame images in the appropriate meeting directory
2. Ensure the filename matches the `frame_path` in the JSON data
3. The images will automatically display in the vote viewer

## Image Requirements

- Format: JPG
- Size: Recommended max 1200px width
- Quality: High enough to read vote results clearly
"""
    
    with open('frame_images/README.md', 'w') as f:
        f.write(readme_content)
    
    print(f"\n✅ Created {len(created_dirs)} frame directories!")
    print(f"📁 Frame images should be placed in the created directories")
    print(f"📋 See frame_images/README.md for instructions")

if __name__ == "__main__":
    create_frame_directories()
