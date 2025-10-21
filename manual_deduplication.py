#!/usr/bin/env python3
"""
Manual Deduplication - Remove specific duplicate votes identified in analysis
"""

import json

def manual_deduplication():
    """Manually remove specific duplicate votes based on frame analysis"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== MANUAL DEDUPLICATION ===")

    # Get all votes
    all_votes = data['votes']
    print(f"Starting with {len(all_votes)} votes")

    # Define votes to remove based on our analysis
    # These are the lower-quality duplicates we identified
    votes_to_remove = set()

    # Meeting 14262 - Remove duplicates on same frames
    meeting_14262_votes = [vote for vote in all_votes if vote.get('meeting_id') == '14262']
    print(f"\n🔍 Meeting 14262: {len(meeting_14262_votes)} votes")

    # Group by frame number
    frame_groups = {}
    for vote in meeting_14262_votes:
        frame_num = vote.get('frame_number')
        if frame_num is not None and frame_num != 'N/A':
            try:
                frame_num = int(frame_num)
                if frame_num not in frame_groups:
                    frame_groups[frame_num] = []
                frame_groups[frame_num].append(vote)
            except (ValueError, TypeError):
                continue

    # Remove duplicates from each frame group
    for frame_num, votes in frame_groups.items():
        if len(votes) > 1:
            print(f"  Frame {frame_num}: {len(votes)} votes")

            # Sort by agenda item length (keep longer descriptions)
            votes_with_length = []
            for vote in votes:
                agenda_item = vote.get('agenda_item')
                if isinstance(agenda_item, dict):
                    length = len(agenda_item.get('description', ''))
                elif isinstance(agenda_item, str):
                    length = len(agenda_item)
                else:
                    length = 0
                votes_with_length.append((length, vote))

            votes_with_length.sort(key=lambda x: x[0], reverse=True)

            # Keep the first (longest) vote, remove the rest
            for i, (length, vote) in enumerate(votes_with_length):
                if i == 0:
                    print(f"    ✅ Keeping: {vote.get('id')} (length: {length})")
                else:
                    votes_to_remove.add(vote.get('id'))
                    print(f"    ❌ Removing: {vote.get('id')} (length: {length})")

    # Meeting 14319 - Remove duplicates on same frames
    meeting_14319_votes = [vote for vote in all_votes if vote.get('meeting_id') == '14319']
    print(f"\n🔍 Meeting 14319: {len(meeting_14319_votes)} votes")

    frame_groups = {}
    for vote in meeting_14319_votes:
        frame_num = vote.get('frame_number')
        if frame_num is not None and frame_num != 'N/A':
            try:
                frame_num = int(frame_num)
                if frame_num not in frame_groups:
                    frame_groups[frame_num] = []
                frame_groups[frame_num].append(vote)
            except (ValueError, TypeError):
                continue

    for frame_num, votes in frame_groups.items():
        if len(votes) > 1:
            print(f"  Frame {frame_num}: {len(votes)} votes")

            # Sort by agenda item length
            votes_with_length = []
            for vote in votes:
                agenda_item = vote.get('agenda_item')
                if isinstance(agenda_item, dict):
                    length = len(agenda_item.get('description', ''))
                elif isinstance(agenda_item, str):
                    length = len(agenda_item)
                else:
                    length = 0
                votes_with_length.append((length, vote))

            votes_with_length.sort(key=lambda x: x[0], reverse=True)

            # Keep the first (longest) vote, remove the rest
            for i, (length, vote) in enumerate(votes_with_length):
                if i == 0:
                    print(f"    ✅ Keeping: {vote.get('id')} (length: {length})")
                else:
                    votes_to_remove.add(vote.get('id'))
                    print(f"    ❌ Removing: {vote.get('id')} (length: {length})")

    # Meeting 14350 - Remove duplicates on same frames
    meeting_14350_votes = [vote for vote in all_votes if vote.get('meeting_id') == '14350']
    print(f"\n🔍 Meeting 14350: {len(meeting_14350_votes)} votes")

    frame_groups = {}
    for vote in meeting_14350_votes:
        frame_num = vote.get('frame_number')
        if frame_num is not None and frame_num != 'N/A':
            try:
                frame_num = int(frame_num)
                if frame_num not in frame_groups:
                    frame_groups[frame_num] = []
                frame_groups[frame_num].append(vote)
            except (ValueError, TypeError):
                continue

    for frame_num, votes in frame_groups.items():
        if len(votes) > 1:
            print(f"  Frame {frame_num}: {len(votes)} votes")

            # Sort by agenda item length
            votes_with_length = []
            for vote in votes:
                agenda_item = vote.get('agenda_item')
                if isinstance(agenda_item, dict):
                    length = len(agenda_item.get('description', ''))
                elif isinstance(agenda_item, str):
                    length = len(agenda_item)
                else:
                    length = 0
                votes_with_length.append((length, vote))

            votes_with_length.sort(key=lambda x: x[0], reverse=True)

            # Keep the first (longest) vote, remove the rest
            for i, (length, vote) in enumerate(votes_with_length):
                if i == 0:
                    print(f"    ✅ Keeping: {vote.get('id')} (length: {length})")
                else:
                    votes_to_remove.add(vote.get('id'))
                    print(f"    ❌ Removing: {vote.get('id')} (length: {length})")

    # Remove the identified duplicates
    print(f"\n📊 Removing {len(votes_to_remove)} duplicate votes...")
    data['votes'] = [vote for vote in data['votes'] if vote.get('id') not in votes_to_remove]

    print(f"✅ Removed {len(votes_to_remove)} duplicate votes")
    print(f"✅ Final vote count: {len(data['votes'])}")

    # Update meeting metadata
    print(f"\n📊 Updating meeting metadata...")
    meetings_updated = 0

    for meeting_id in ['14262', '14319', '14350']:
        meeting_votes = [vote for vote in data['votes'] if vote.get('meeting_id') == meeting_id]
        meeting_data = data.get('meetings', {}).get(meeting_id, {})

        if meeting_data:
            new_total_votes = len(meeting_votes)
            new_passed_votes = sum(1 for vote in meeting_votes if 'pass' in vote.get('result', '').lower())
            new_failed_votes = sum(1 for vote in meeting_votes if 'fail' in vote.get('result', '').lower())

            if (meeting_data.get('total_votes') != new_total_votes or
                meeting_data.get('passed_votes') != new_passed_votes or
                meeting_data.get('failed_votes') != new_failed_votes):

                print(f"  Meeting {meeting_id}: {meeting_data.get('total_votes', 'N/A')} → {new_total_votes} votes")
                meeting_data['total_votes'] = new_total_votes
                meeting_data['passed_votes'] = new_passed_votes
                meeting_data['failed_votes'] = new_failed_votes
                meetings_updated += 1

    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ MANUAL DEDUPLICATION COMPLETE!")
    print(f"📊 Summary:")
    print(f"  - Total votes removed: {len(votes_to_remove)}")
    print(f"  - Meetings updated: {meetings_updated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    manual_deduplication()
