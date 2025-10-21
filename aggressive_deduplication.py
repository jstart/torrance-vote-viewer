#!/usr/bin/env python3
"""
Aggressive Deduplication for Frame-Based Duplicates
Removes duplicate votes based on frame proximity and keeps the best quality vote.
"""

import json
from collections import defaultdict

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

    # Penalize votes with truncated descriptions
    if isinstance(agenda_item, str) and ('...' in agenda_item or len(agenda_item) < 20):
        score -= 50

    return score

def aggressive_deduplication():
    """Aggressively remove duplicate votes based on frame proximity"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== AGGRESSIVE DEDUPLICATION ===")

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
                print(f"  Frame {frame_num}: {len(votes)} votes - removing duplicates")

                # Score all votes
                scored_votes = []
                for vote in votes:
                    score = get_vote_quality_score(vote)
                    scored_votes.append((score, vote))

                # Sort by score (highest first)
                scored_votes.sort(key=lambda x: x[0], reverse=True)

                # Keep the highest scoring vote
                best_vote = scored_votes[0][1]
                votes_to_keep.add(best_vote['id'])
                print(f"    ✅ Keeping: {best_vote['id']} (score: {scored_votes[0][0]})")
                print(f"        Agenda: {str(vote.get('agenda_item', 'N/A'))[:60]}...")

                # Mark others for removal
                for score, vote in scored_votes[1:]:
                    votes_to_remove.add(vote['id'])
                    print(f"    ❌ Removing: {vote['id']} (score: {score})")
                    print(f"        Agenda: {str(vote.get('agenda_item', 'N/A'))[:60]}...")
            else:
                # Single vote for this frame - keep it
                votes_to_keep.add(votes[0]['id'])

        # Also check for votes with very close frame numbers (adjacent frames)
        print(f"  Checking for adjacent frame duplicates...")
        frame_votes = [(int(v.get('frame_number')), v) for v in meeting_votes
                      if v.get('frame_number') is not None and v.get('frame_number') != 'N/A']
        frame_votes.sort(key=lambda x: x[0])

        for i in range(len(frame_votes) - 1):
            frame1, vote1 = frame_votes[i]
            frame2, vote2 = frame_votes[i + 1]
            diff = frame2 - frame1

            if diff <= 2 and vote1['id'] not in votes_to_remove and vote2['id'] not in votes_to_remove:
                # Very close frames - likely duplicates
                score1 = get_vote_quality_score(vote1)
                score2 = get_vote_quality_score(vote2)

                if score1 >= score2:
                    votes_to_remove.add(vote2['id'])
                    votes_to_keep.add(vote1['id'])
                    print(f"    ❌ Removing adjacent: {vote2['id']} (frame {frame2}, score: {score2})")
                    print(f"    ✅ Keeping: {vote1['id']} (frame {frame1}, score: {score1})")
                else:
                    votes_to_remove.add(vote1['id'])
                    votes_to_keep.add(vote2['id'])
                    print(f"    ❌ Removing adjacent: {vote1['id']} (frame {frame1}, score: {score1})")
                    print(f"    ✅ Keeping: {vote2['id']} (frame {frame2}, score: {score2})")

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

    print(f"\n✅ AGGRESSIVE DEDUPLICATION COMPLETE!")
    print(f"📊 Summary:")
    print(f"  - Total votes removed: {total_removed}")
    print(f"  - Total votes kept: {total_kept}")
    print(f"  - Meetings updated: {meetings_updated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    aggressive_deduplication()
