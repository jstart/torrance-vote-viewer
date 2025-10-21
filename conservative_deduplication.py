#!/usr/bin/env python3
"""
Conservative Deduplication for Frame-Based Duplicates
Only removes obvious duplicates (same frame number with identical/similar content).
"""

import json
from collections import defaultdict

def are_votes_similar(vote1, vote2):
    """Check if two votes are likely duplicates"""
    # Check if same frame number
    frame1 = vote1.get('frame_number')
    frame2 = vote2.get('frame_number')

    if frame1 != frame2:
        return False

    # Check if agenda items are similar
    agenda1 = vote1.get('agenda_item')
    agenda2 = vote2.get('agenda_item')

    # Extract text for comparison
    if isinstance(agenda1, dict):
        text1 = agenda1.get('description', '')
    else:
        text1 = str(agenda1) if agenda1 else ''

    if isinstance(agenda2, dict):
        text2 = agenda2.get('description', '')
    else:
        text2 = str(agenda2) if agenda2 else ''

    # Check for exact match
    if text1 == text2:
        return True

    # Check for very similar content (one is truncated version of other)
    if text1 and text2:
        if text1 in text2 or text2 in text1:
            return True

        # Check if one is just a number/letter (like "10A" vs "10A. Full description")
        if len(text1) <= 5 and text2.startswith(text1):
            return True
        if len(text2) <= 5 and text1.startswith(text2):
            return True

    return False

def get_vote_quality_score(vote):
    """Score votes to determine quality - higher is better"""
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

    # Prioritize votes with longer agenda descriptions
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

    # Penalize votes with very short descriptions (likely truncated)
    if isinstance(agenda_item, str) and len(agenda_item) < 10:
        score -= 30

    return score

def conservative_deduplication():
    """Conservatively remove only obvious duplicates"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== CONSERVATIVE DEDUPLICATION ===")

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

                # Group similar votes together
                similar_groups = []
                processed_votes = set()

                for i, vote1 in enumerate(votes):
                    if vote1['id'] in processed_votes:
                        continue

                    similar_group = [vote1]
                    processed_votes.add(vote1['id'])

                    for j, vote2 in enumerate(votes[i+1:], i+1):
                        if vote2['id'] in processed_votes:
                            continue

                        if are_votes_similar(vote1, vote2):
                            similar_group.append(vote2)
                            processed_votes.add(vote2['id'])

                    if len(similar_group) > 1:
                        similar_groups.append(similar_group)
                    else:
                        # Single vote - keep it
                        votes_to_keep.add(vote1['id'])

                # Process each group of similar votes
                for group in similar_groups:
                    print(f"    Found {len(group)} similar votes on frame {frame_num}")

                    # Score all votes in this group
                    scored_votes = []
                    for vote in group:
                        score = get_vote_quality_score(vote)
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

    print(f"\n✅ CONSERVATIVE DEDUPLICATION COMPLETE!")
    print(f"📊 Summary:")
    print(f"  - Total votes removed: {total_removed}")
    print(f"  - Total votes kept: {total_kept}")
    print(f"  - Meetings updated: {meetings_updated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    conservative_deduplication()
