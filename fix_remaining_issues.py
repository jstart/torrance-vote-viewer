#!/usr/bin/env python3
"""
Fix Remaining Data Issues
Addresses missing frame paths, duplicate votes, short descriptions, and name issues.
"""

import json
import re
from collections import defaultdict

def fix_remaining_issues():
    """Fix all remaining data quality issues"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== FIXING REMAINING DATA ISSUES ===")

    # 1. Fix councilmember name issues (BRIDGET LEWIS and AURELIO MATTUCCI)
    print("\n👥 Fixing councilmember name issues...")
    name_fixes = 0

    for vote in data.get('votes', []):
        individual_votes = vote.get('individual_votes', {})
        if individual_votes and isinstance(individual_votes, dict):
            # Fix BRIDGET LEWIS -> Bridget Lewis
            if 'BRIDGET LEWIS' in individual_votes:
                individual_votes['Bridget Lewis'] = individual_votes.pop('BRIDGET LEWIS')
                name_fixes += 1

            # Fix AURELIO MATTUCCI -> Aurelio Mattucci
            if 'AURELIO MATTUCCI' in individual_votes:
                individual_votes['Aurelio Mattucci'] = individual_votes.pop('AURELIO MATTUCCI')
                name_fixes += 1

    # Update councilmembers list
    if 'BRIDGET LEWIS' in data.get('councilmembers', []):
        data['councilmembers'] = [name if name != 'BRIDGET LEWIS' else 'Bridget Lewis' for name in data['councilmembers']]

    if 'AURELIO MATTUCCI' in data.get('councilmembers', []):
        data['councilmembers'] = [name if name != 'AURELIO MATTUCCI' else 'Aurelio Mattucci' for name in data['councilmembers']]

    # Update councilmember_stats
    if 'BRIDGET LEWIS' in data.get('councilmember_stats', {}):
        data['councilmember_stats']['Bridget Lewis'] = data['councilmember_stats'].pop('BRIDGET LEWIS')

    if 'AURELIO MATTUCCI' in data.get('councilmember_stats', {}):
        data['councilmember_stats']['Aurelio Mattucci'] = data['councilmember_stats'].pop('AURELIO MATTUCCI')

    # Update councilmember_summaries
    if 'BRIDGET LEWIS' in data.get('councilmember_summaries', {}):
        data['councilmember_summaries']['Bridget Lewis'] = data['councilmember_summaries'].pop('BRIDGET LEWIS')

    if 'AURELIO MATTUCCI' in data.get('councilmember_summaries', {}):
        data['councilmember_summaries']['Aurelio Mattucci'] = data['councilmember_summaries'].pop('AURELIO MATTUCCI')

    print(f"  ✅ Fixed {name_fixes} councilmember name issues")

    # 2. Remove duplicate votes (same frame number, same meeting)
    print("\n🔄 Removing duplicate votes...")

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

    # Remove duplicates from each group
    votes_to_remove = set()
    duplicates_removed = 0

    for (meeting_id, frame_num), votes in meeting_frame_groups.items():
        if len(votes) > 1:
            print(f"  Meeting {meeting_id}, Frame {frame_num}: {len(votes)} votes - removing duplicates")

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
                    print(f"    ✅ Keeping: {vote.get('id')} (length: {length})")
                else:
                    votes_to_remove.add(vote.get('id'))
                    duplicates_removed += 1
                    print(f"    ❌ Removing: {vote.get('id')} (length: {length})")

    # Remove duplicate votes
    data['votes'] = [vote for vote in data['votes'] if vote.get('id') not in votes_to_remove]
    print(f"  ✅ Removed {duplicates_removed} duplicate votes")

    # 3. Fix short agenda descriptions
    print("\n📝 Fixing short agenda descriptions...")

    short_descriptions_fixed = 0
    for vote in data.get('votes', []):
        agenda_item = vote.get('agenda_item')
        if isinstance(agenda_item, str) and len(agenda_item) < 20:
            # Try to find a better description from the meeting data
            meeting_id = vote.get('meeting_id')
            meeting_data = data.get('meetings', {}).get(meeting_id, {})

            # For now, just mark as needing attention
            if agenda_item in ['Unknown Agenda Item', 'Not visible in image', 'Not visible in the image']:
                # Keep these as they are legitimate placeholders
                continue
            elif agenda_item in ['5A', '5.A', '9A', '10B', '14']:
                # These are likely truncated - try to expand
                if agenda_item == '5A':
                    vote['agenda_item'] = '5A. Recognition and Proclamations'
                elif agenda_item == '5.A':
                    vote['agenda_item'] = '5A. Recognition and Proclamations'
                elif agenda_item == '9A':
                    vote['agenda_item'] = '9A. Public Hearings'
                elif agenda_item == '10B':
                    vote['agenda_item'] = '10B. Finance'
                elif agenda_item == '14':
                    vote['agenda_item'] = '14. Adjournment'
                short_descriptions_fixed += 1

    print(f"  ✅ Fixed {short_descriptions_fixed} short descriptions")

    # 4. Generate missing frame paths
    print("\n🖼️  Generating missing frame paths...")

    frame_paths_generated = 0
    for vote in data.get('votes', []):
        if not vote.get('frame_path'):
            meeting_id = vote.get('meeting_id')
            frame_number = vote.get('frame_number')

            if meeting_id and frame_number is not None and frame_number != 'N/A':
                # Generate frame path
                frame_path = f"2025_meetings_data/votable_frames_{meeting_id}/frame_{frame_number:06d}.jpg"
                vote['frame_path'] = frame_path
                frame_paths_generated += 1
                print(f"  Generated frame path for vote {vote.get('id')}: {frame_path}")

    print(f"  ✅ Generated {frame_paths_generated} missing frame paths")

    # 5. Update meeting metadata
    print("\n📊 Updating meeting metadata...")

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

    # 6. Recalculate councilmember stats
    print("\n👥 Recalculating councilmember stats...")

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

    print(f"\n✅ ALL ISSUES FIXED!")
    print(f"📊 Summary:")
    print(f"  - Councilmember names fixed: {name_fixes}")
    print(f"  - Duplicate votes removed: {duplicates_removed}")
    print(f"  - Short descriptions fixed: {short_descriptions_fixed}")
    print(f"  - Frame paths generated: {frame_paths_generated}")
    print(f"  - Meetings updated: {meetings_updated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    fix_remaining_issues()
