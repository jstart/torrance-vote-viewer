#!/usr/bin/env python3
"""
2021 Torrance Vote Processor - Usage Examples
=============================================

This script demonstrates how to use the 2021 Torrance vote processor
with various options and configurations.

Usage:
    python 2021_usage_examples.py
"""

import subprocess
import sys
import os
import json
from pathlib import Path

def run_command(cmd, description):
    """Run a command and display results"""
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            print("✅ SUCCESS")
            if result.stdout:
                print("Output:")
                print(result.stdout)
        else:
            print("❌ FAILED")
            if result.stderr:
                print("Error:")
                print(result.stderr)

    except subprocess.TimeoutExpired:
        print("⏰ TIMEOUT - Command took too long")
    except Exception as e:
        print(f"❌ ERROR: {e}")

def show_file_contents(filepath, description, limit=20):
    """Show contents of a file"""
    print(f"\n{'='*60}")
    print(f"📄 {description}")
    print(f"{'='*60}")
    print(f"File: {filepath}")
    print()

    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            lines = content.split('\n')
            if len(lines) > limit:
                print('\n'.join(lines[:limit]))
                print(f"\n... ({len(lines) - limit} more lines)")
            else:
                print(content)

        except Exception as e:
            print(f"❌ Error reading file: {e}")
    else:
        print("❌ File not found")

def main():
    """Main demonstration"""
    print("🚀 2021 Torrance Vote Processor - Usage Examples")
    print("="*60)

    # Check if we're in the right directory
    if not os.path.exists("process_2021_complete.py"):
        print("❌ Please run this script from the torrance-vote-viewer directory")
        sys.exit(1)

    # Example 1: Discover meetings
    run_command(
        ["python", "discover_2021_meetings.py", "--verbose"],
        "Example 1: Discover 2021 meetings"
    )

    # Example 2: Download frames for a single meeting
    run_command(
        ["python", "download_2021_frames.py", "--meeting-id", "12001", "--verbose"],
        "Example 2: Download frames for single meeting"
    )

    # Example 3: Process a single meeting
    run_command(
        ["python", "process_all_2021_votable_sequential.py", "--meetings", "1", "--verbose"],
        "Example 3: Process single meeting"
    )

    # Example 4: Complete workflow
    run_command(
        ["python", "process_2021_complete.py", "--meetings", "3", "--verbose"],
        "Example 4: Complete workflow (3 meetings)"
    )

    # Show generated files
    show_file_contents("2021_meetings.json", "Generated meetings file", 10)
    show_file_contents("2021_meetings_data/comprehensive_2021_results.json", "Comprehensive results")

    # Show individual meeting results
    backup_dir = Path("data/backup")
    if backup_dir.exists():
        meeting_files = list(backup_dir.glob("votable_meeting_summary_*_sequential.json"))
        if meeting_files:
            show_file_contents(str(meeting_files[0]), "Individual meeting result", 30)

    print("\n" + "="*60)
    print("🎉 USAGE EXAMPLES COMPLETE!")
    print("="*60)
    print("\n📋 Available Commands:")
    print("  python discover_2021_meetings.py                    # Discover meetings")
    print("  python download_2021_frames.py --meeting-id 12001   # Download frames")
    print("  python process_all_2021_votable_sequential.py       # Process meetings")
    print("  python process_2021_complete.py                     # Complete workflow")
    print("\n📁 Generated Files:")
    print("  - 2021_meetings.json                                # Meeting list")
    print("  - 2021_meetings_data/                               # Frame data")
    print("  - data/backup/votable_meeting_summary_*_sequential.json # Individual results")
    print("  - 2021_meetings_data/comprehensive_2021_results.json  # Summary results")
    print("\n🔧 Options:")
    print("  --meetings N        # Process only N meetings")
    print("  --meeting-id ID    # Process single meeting")
    print("  --resume ID        # Resume from meeting ID")
    print("  --gemini-key KEY    # Use Gemini API key")
    print("  --verbose          # Enable verbose logging")
    print("="*60)

if __name__ == '__main__':
    main()
