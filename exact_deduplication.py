#!/usr/bin/env python3
"""
Exact deduplication to remove remaining exact duplicates
"""

import json
from collections import defaultdict

def get_vote_score(vote):
    """Score votes to determine which duplicate to keep"""
    score = 0

    # Prioritize votes with a proper ID
    if vote.get('id'):
        score += 100

    # Prioritize 'Passes' results
    result = vote.get('result', '').lower()
    if 'pass' in result:
        score += 50
    elif 'fail' in result:
        score -= 50

    # Penalize votes that passed with 0 ayes (likely incorrect)
    if 'pass' in result and vote.get('vote_tally', {}).get('ayes', 0) == 0:
        score -= 30

    # Prioritize votes with more individual votes recorded
    if vote.get('individual_votes') and isinstance(vote['individual_votes'], dict):
        score += len(vote['individual_votes']) * 2

    # Prioritize votes with frame_path (more complete data)
    if vote.get('frame_path'):
        score += 10

    # Prioritize votes with motion_text
    if vote.get('motion_text'):
        score += 5

    return score

def exact_deduplication():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print(f"Starting with {len(data['votes'])} votes")

    # Group votes by meeting_id and exact agenda_item
    vote_groups = defaultdict(list)

    for vote in data['votes']:
        meeting_id = vote.get('meeting_id', '')
        agenda_item = vote.get('agenda_item', '')

        # Create a key for grouping
        group_key = f"{meeting_id}|||{agenda_item}"
        vote_groups[group_key].append(vote)

    # Find and process duplicate groups
    duplicates_found = 0
    votes_removed = 0
    kept_votes = []

    for group_key, votes in vote_groups.items():
        if len(votes) > 1:
            duplicates_found += 1
            meeting_id, agenda = group_key.split('|||', 1)

            print(f"\nExact duplicate group {duplicates_found}: Meeting {meeting_id}")
            print(f"Agenda: {agenda[:80]}...")
            print(f"Found {len(votes)} duplicate votes")

            # Score each vote and keep the best one
            scored_votes = [(vote, get_vote_score(vote)) for vote in votes]
            scored_votes.sort(key=lambda x: x[1], reverse=True)

            best_vote = scored_votes[0][0]
            best_score = scored_votes[0][1]

            print(f"Keeping vote with score {best_score}: {best_vote.get('id', 'no-id')}")
            print(f"Result: {best_vote.get('result', 'unknown')}")
            print(f"Individual votes: {len(best_vote.get('individual_votes', {}))}")

            kept_votes.append(best_vote)
            votes_removed += len(votes) - 1

            # Show what was removed
            for vote, score in scored_votes[1:]:
                print(f"  Removed vote with score {score}: {vote.get('id', 'no-id')} - {vote.get('result', 'unknown')}")
        else:
            # No duplicates, keep the single vote
            kept_votes.append(votes[0])

    # Update the data
    data['votes'] = kept_votes

    # Update meeting metadata
    meetings = data.get('meetings', {})
    for meeting_id, meeting_data in meetings.items():
        meeting_votes = [vote for vote in data['votes'] if vote.get('meeting_id') == meeting_id]

        meeting_data['total_votes'] = len(meeting_votes)
        meeting_data['passed_votes'] = sum(1 for vote in meeting_votes if 'pass' in vote.get('result', '').lower())
        meeting_data['failed_votes'] = sum(1 for vote in meeting_votes if 'fail' in vote.get('result', '').lower())

    # Update total counts
    data['total_votes'] = len(data['votes'])
    data['total_meetings'] = len(meetings)

    # Save the deduplicated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Exact deduplication complete!")
    print(f"📊 Duplicate groups found: {duplicates_found}")
    print(f"🗑️ Votes removed: {votes_removed}")
    print(f"📈 Final vote count: {len(data['votes'])}")
    print(f"🏛️ Meetings: {len(meetings)}")

if __name__ == "__main__":
    exact_deduplication()
