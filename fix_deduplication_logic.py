#!/usr/bin/env python3
"""
Fix deduplication logic to prioritize PASSED votes and correct vote tallies
"""

import json
from collections import defaultdict

def fix_deduplication_logic():
    # Load the current data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print(f"Processing {len(data['votes'])} votes...")

    # Group votes by meeting_id and agenda_item
    grouped_votes = defaultdict(list)

    for vote in data['votes']:
        meeting_id = vote.get('meeting_id', '')
        agenda_item = vote.get('agenda_item', '')
        key = f"{meeting_id}|{agenda_item}"
        grouped_votes[key].append(vote)

    # Find duplicates
    duplicates = {key: votes for key, votes in grouped_votes.items() if len(votes) > 1}

    print(f"\nFound {len(duplicates)} groups with duplicate votes:")

    # Create deduplicated votes list
    deduplicated_votes = []
    votes_removed = 0

    for key, votes in grouped_votes.items():
        if len(votes) == 1:
            # Single vote, keep as-is
            deduplicated_votes.append(votes[0])
        else:
            # Multiple votes, choose the best one using improved logic
            print(f"\nDeduplicating: {key}")

            # Strategy: Prioritize votes that actually passed and have reasonable vote tallies
            def vote_quality_score(vote):
                score = 0

                # Prefer votes with proper IDs
                if vote.get('id') and vote.get('id') != '':
                    score += 100

                # Prefer PASSED votes over FAILED votes
                result = vote.get('result', '').lower()
                if 'pass' in result:
                    score += 50
                elif 'fail' in result:
                    score -= 50

                # Prefer votes with reasonable vote tallies (not 0 ayes when it should pass)
                vote_tally = vote.get('vote_tally', {})
                ayes = vote_tally.get('ayes', 0)
                noes = vote_tally.get('noes', 0)

                # If it's marked as passed but has 0 ayes, that's suspicious
                if 'pass' in result and ayes == 0:
                    score -= 30

                # Prefer votes with more individual votes (more complete data)
                individual_votes = vote.get('individual_votes', {})
                score += len(individual_votes) * 2

                return score

            # Sort by quality score (highest first)
            votes.sort(key=vote_quality_score, reverse=True)
            best_vote = votes[0]

            deduplicated_votes.append(best_vote)
            votes_removed += len(votes) - 1

            print(f"  Kept: {best_vote.get('result', 'Unknown')} - {best_vote.get('vote_tally', {})}")
            print(f"  Removed: {len(votes) - 1} duplicate(s)")

    print(f"\n✅ Improved deduplication complete!")
    print(f"Original votes: {len(data['votes'])}")
    print(f"Deduplicated votes: {len(deduplicated_votes)}")
    print(f"Votes removed: {votes_removed}")

    # Update the data
    data['votes'] = deduplicated_votes

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("✅ Corrected deduplicated data saved!")

if __name__ == "__main__":
    fix_deduplication_logic()
