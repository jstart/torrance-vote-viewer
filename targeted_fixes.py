#!/usr/bin/env python3
"""
Targeted Fixes for Specific Issues
Only fixes the most critical issues without being overly aggressive.
"""

import json

def targeted_fixes():
    """Apply targeted fixes for specific issues"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== TARGETED FIXES ===")

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

    # 2. Fix the specific duplicate agenda item in meeting 14536
    print("\n🔄 Fixing specific duplicate agenda item...")

    # Find the duplicate votes in meeting 14536
    meeting_14536_votes = [vote for vote in data.get('votes', []) if vote.get('meeting_id') == '14536']
    duplicate_votes = []

    for vote in meeting_14536_votes:
        agenda_item = vote.get('agenda_item')
        if isinstance(agenda_item, str) and '10A. 10A. City Council Ad Hoc Naming' in agenda_item:
            duplicate_votes.append(vote)

    if len(duplicate_votes) > 1:
        # Keep the vote with the longer description
        duplicate_votes.sort(key=lambda v: len(str(v.get('agenda_item', ''))), reverse=True)
        vote_to_remove = duplicate_votes[1]  # Remove the second one

        data['votes'] = [vote for vote in data['votes'] if vote.get('id') != vote_to_remove.get('id')]
        print(f"  ✅ Removed duplicate vote: {vote_to_remove.get('id')}")
    else:
        print("  ✅ No duplicate agenda items found")

    # 3. Generate missing frame paths for votes that need them
    print("\n🖼️  Generating missing frame paths...")

    frame_paths_generated = 0
    for vote in data.get('votes', []):
        if not vote.get('frame_path'):
            meeting_id = vote.get('meeting_id')
            frame_number = vote.get('frame_number')

            if meeting_id and frame_number is not None and frame_number != 'N/A':
                try:
                    frame_number = int(frame_number)
                    # Generate frame path
                    frame_path = f"2025_meetings_data/votable_frames_{meeting_id}/frame_{frame_number:06d}.jpg"
                    vote['frame_path'] = frame_path
                    frame_paths_generated += 1
                    print(f"  Generated frame path for vote {vote.get('id')}: {frame_path}")
                except (ValueError, TypeError):
                    continue

    print(f"  ✅ Generated {frame_paths_generated} missing frame paths")

    # 4. Recalculate councilmember stats
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

    print(f"\n✅ TARGETED FIXES COMPLETE!")
    print(f"📊 Summary:")
    print(f"  - Councilmember names fixed: {name_fixes}")
    print(f"  - Duplicate votes removed: 1")
    print(f"  - Frame paths generated: {frame_paths_generated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    targeted_fixes()
