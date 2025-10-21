#!/usr/bin/env python3
"""
Fix Frame-Based Duplicates
Removes duplicate votes caused by processing artifacts where adjacent frames
or same frames were processed multiple times.
"""

import json
import re
from collections import defaultdict

def normalize_agenda_item(agenda_item):
    """Normalize agenda item for better matching"""
    if not agenda_item:
        return ""

    if isinstance(agenda_item, dict):
        number = agenda_item.get('number', '')
        description = agenda_item.get('description', '')
        agenda_item = f"{number}. {description}".strip()

    # Convert to lowercase and clean up
    normalized = str(agenda_item).lower().strip()

    # Remove common prefixes/suffixes that don't affect meaning
    normalized = re.sub(r'^(item\s+\d+\s*:\s*)', '', normalized)
    normalized = re.sub(r'^(no\.\s*\d+\s*)', '', normalized)
    normalized = re.sub(r'\s*\(for adoption only\)\s*$', '', normalized)
    normalized = re.sub(r'\s*\(for presentation\)\s*$', '', normalized)
    normalized = re.sub(r'\s*expenditure:\s*none\.?\s*$', '', normalized)
    normalized = re.sub(r'\s*expenditure:\s*\$[0-9,]+\.?\s*$', '', normalized)

    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized

def get_vote_score(vote):
    """Score votes to determine which duplicate to keep"""
    score = 0

    # Prioritize votes with proper IDs
    if vote.get('id'):
        score += 100

    # Prioritize votes with complete individual vote data
    individual_votes = vote.get('individual_votes', {})
    if individual_votes and isinstance(individual_votes, dict):
        score += len(individual_votes) * 10

    # Prioritize votes with complete vote tally
    vote_tally = vote.get('vote_tally', {})
    if vote_tally and isinstance(vote_tally, dict):
        total_tally = vote_tally.get('ayes', 0) + vote_tally.get('noes', 0) + vote_tally.get('abstentions', 0)
        if total_tally > 0:
            score += total_tally * 5

    # Prioritize votes with longer agenda descriptions (more complete)
    agenda_item = vote.get('agenda_item')
    if isinstance(agenda_item, dict):
        desc_length = len(agenda_item.get('description', ''))
    elif isinstance(agenda_item, str):
        desc_length = len(agenda_item)
    else:
        desc_length = 0

    score += desc_length

    # Prioritize votes with frame paths
    if vote.get('frame_path'):
        score += 20

    return score

def fix_frame_duplicates():
    """Fix duplicate votes caused by frame processing artifacts"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== FIXING FRAME-BASED DUPLICATES ===")

    # Focus on problematic meetings
    target_meetings = ['14262', '14319', '14350']

    total_removed = 0
    total_kept = 0

    for meeting_id in target_meetings:
        print(f"\n🔍 Processing meeting {meeting_id}...")

        # Get all votes for this meeting
        meeting_votes = [vote for vote in data['votes'] if vote.get('meeting_id') == meeting_id]
        print(f"  Found {len(meeting_votes)} votes")

        if not meeting_votes:
            continue

        # Group votes by frame number
        frame_groups = defaultdict(list)
        for vote in meeting_votes:
            frame_num = vote.get('frame_number')
            if frame_num is not None and frame_num != 'N/A':
                try:
                    frame_groups[int(frame_num)].append(vote)
                except (ValueError, TypeError):
                    continue

        # Process each frame group
        votes_to_remove = set()
        votes_to_keep = set()

        for frame_num, votes in frame_groups.items():
            if len(votes) > 1:
                print(f"  Frame {frame_num}: {len(votes)} votes - checking for duplicates")

                # Group by normalized agenda item
                agenda_groups = defaultdict(list)
                for vote in votes:
                    agenda_item = vote.get('agenda_item')
                    normalized = normalize_agenda_item(agenda_item)
                    agenda_groups[normalized].append(vote)

                # Process each agenda group
                for agenda_key, agenda_votes in agenda_groups.items():
                    if len(agenda_votes) > 1:
                        print(f"    Duplicate agenda: '{agenda_key[:50]}...' ({len(agenda_votes)} votes)")

                        # Score all votes in this group
                        scored_votes = []
                        for vote in agenda_votes:
                            score = get_vote_score(vote)
                            scored_votes.append((score, vote))

                        # Sort by score (highest first)
                        scored_votes.sort(key=lambda x: x[0], reverse=True)

                        # Keep the highest scoring vote
                        best_vote = scored_votes[0][1]
                        votes_to_keep.add(best_vote['id'])
                        print(f"      ✅ Keeping: {best_vote['id']} (score: {scored_votes[0][0]})")

                        # Mark others for removal
                        for score, vote in scored_votes[1:]:
                            votes_to_remove.add(vote['id'])
                            print(f"      ❌ Removing: {vote['id']} (score: {score})")
                    else:
                        # Single vote in agenda group - keep it
                        votes_to_keep.add(agenda_votes[0]['id'])
            else:
                # Single vote for this frame - keep it
                votes_to_keep.add(votes[0]['id'])

        # Remove duplicate votes
        original_count = len(data['votes'])
        data['votes'] = [vote for vote in data['votes']
                        if vote.get('id') not in votes_to_remove]
        removed_count = original_count - len(data['votes'])

        print(f"  ✅ Removed {removed_count} duplicate votes")
        print(f"  ✅ Kept {len(votes_to_keep)} unique votes")

        total_removed += removed_count
        total_kept += len(votes_to_keep)

    # Update meeting metadata
    print(f"\n📊 Updating meeting metadata...")
    meetings_updated = 0

    for meeting_id, meeting_data in data.get('meetings', {}).items():
        if meeting_id in target_meetings:
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

    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ DUPLICATE REMOVAL COMPLETE!")
    print(f"📊 Summary:")
    print(f"  - Total votes removed: {total_removed}")
    print(f"  - Total votes kept: {total_kept}")
    print(f"  - Meetings updated: {meetings_updated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    fix_frame_duplicates()
