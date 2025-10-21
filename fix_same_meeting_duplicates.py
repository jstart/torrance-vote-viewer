#!/usr/bin/env python3
"""
Fix Same-Meeting Duplicate Frame Numbers
Remove duplicate votes that have the same frame number within the same meeting.
"""

import json
from collections import defaultdict

def fix_same_meeting_duplicates():
    """Remove duplicate votes with same frame numbers within same meetings"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== FIXING SAME-MEETING DUPLICATE FRAME NUMBERS ===")

    # Group votes by meeting and frame number
    meeting_frame_groups = defaultdict(list)
    for vote in data.get('votes', []):
        meeting_id = vote.get('meeting_id')
        frame_num = vote.get('frame_number')

        if meeting_id and frame_num is not None and frame_num != 'N/A':
            try:
                frame_num = int(frame_num)
                meeting_frame_groups[(meeting_id, frame_num)].append(vote)
            except (ValueError, TypeError):
                continue

    # Process each group
    votes_to_remove = set()
    duplicates_removed = 0

    for (meeting_id, frame_num), votes in meeting_frame_groups.items():
        if len(votes) > 1:
            print(f"\n🔍 Meeting {meeting_id}, Frame {frame_num}: {len(votes)} votes - removing duplicates")

            # Sort by agenda description length (keep longest)
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
                    agenda_display = str(vote.get('agenda_item', 'N/A'))[:50]
                    print(f"    ✅ Keeping: {vote.get('id')} (length: {length}) - {agenda_display}...")
                else:
                    votes_to_remove.add(vote.get('id'))
                    duplicates_removed += 1
                    agenda_display = str(vote.get('agenda_item', 'N/A'))[:50]
                    print(f"    ❌ Removing: {vote.get('id')} (length: {length}) - {agenda_display}...")

    # Remove duplicate votes
    original_count = len(data['votes'])
    data['votes'] = [vote for vote in data['votes'] if vote.get('id') not in votes_to_remove]
    removed_count = original_count - len(data['votes'])

    print(f"\n✅ Removed {removed_count} duplicate votes")
    print(f"✅ Final vote count: {len(data['votes'])}")

    # Update meeting metadata
    print(f"\n📊 Updating meeting metadata...")
    meetings_updated = 0

    for meeting_id, meeting_data in data.get('meetings', {}).items():
        meeting_votes = [vote for vote in data['votes'] if vote.get('meeting_id') == meeting_id]

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

    print(f"  ✅ Updated {meetings_updated} meetings")

    # Recalculate councilmember stats
    print(f"\n👥 Recalculating councilmember stats...")

    # Get all unique councilmembers from votes
    all_councilmembers = set()
    for vote in data.get('votes', []):
        individual_votes = vote.get('individual_votes', {})
        if individual_votes and isinstance(individual_votes, dict):
            for cm_name in individual_votes.keys():
                all_councilmembers.add(cm_name)

    # Update councilmembers list
    data['councilmembers'] = sorted(list(all_councilmembers))

    # Recalculate stats
    councilmember_stats = {}
    for cm in all_councilmembers:
        councilmember_stats[cm] = {
            'total_votes': 0,
            'yes_votes': 0,
            'no_votes': 0,
            'abstentions': 0
        }

    for vote in data.get('votes', []):
        individual_votes = vote.get('individual_votes', {})
        if individual_votes and isinstance(individual_votes, dict):
            for cm, vote_result in individual_votes.items():
                if cm in councilmember_stats:
                    councilmember_stats[cm]['total_votes'] += 1
                    if vote_result == 'YES':
                        councilmember_stats[cm]['yes_votes'] += 1
                    elif vote_result == 'NO':
                        councilmember_stats[cm]['no_votes'] += 1
                    elif vote_result == 'ABSTAIN':
                        councilmember_stats[cm]['abstentions'] += 1

    data['councilmember_stats'] = councilmember_stats
    print(f"  ✅ Recalculated stats for {len(all_councilmembers)} councilmembers")

    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ SAME-MEETING DUPLICATES FIXED!")
    print(f"📊 Summary:")
    print(f"  - Duplicate votes removed: {removed_count}")
    print(f"  - Meetings updated: {meetings_updated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    fix_same_meeting_duplicates()
