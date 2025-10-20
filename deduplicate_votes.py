#!/usr/bin/env python3
"""
Find and fix duplicate votes in the consolidated data
"""

import json
from collections import defaultdict

def find_and_fix_duplicates():
    # Load the data
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
    
    total_duplicates = 0
    for key, votes in duplicates.items():
        meeting_id, agenda_item = key.split('|', 1)
        print(f"\nMeeting {meeting_id}: {len(votes)} votes for '{agenda_item[:50]}...'")
        
        for i, vote in enumerate(votes):
            print(f"  Vote {i+1}: {vote.get('result', 'Unknown')} - {vote.get('vote_tally', {})}")
            total_duplicates += 1
    
    print(f"\nTotal duplicate votes: {total_duplicates}")
    
    # Create deduplicated votes list
    deduplicated_votes = []
    votes_removed = 0
    
    for key, votes in grouped_votes.items():
        if len(votes) == 1:
            # Single vote, keep as-is
            deduplicated_votes.append(votes[0])
        else:
            # Multiple votes, choose the best one
            print(f"\nDeduplicating: {key}")
            
            # Strategy: Choose the vote with the most individual votes (most complete data)
            best_vote = max(votes, key=lambda v: len(v.get('individual_votes', {})))
            
            # If there's a tie, choose the one with a proper ID (not empty)
            if len(best_vote.get('individual_votes', {})) == max(len(v.get('individual_votes', {})) for v in votes):
                votes_with_ids = [v for v in votes if v.get('id') and v.get('id') != '']
                if votes_with_ids:
                    best_vote = votes_with_ids[0]
            
            deduplicated_votes.append(best_vote)
            votes_removed += len(votes) - 1
            
            print(f"  Kept: {best_vote.get('result', 'Unknown')} - {best_vote.get('vote_tally', {})}")
            print(f"  Removed: {len(votes) - 1} duplicate(s)")
    
    print(f"\n✅ Deduplication complete!")
    print(f"Original votes: {len(data['votes'])}")
    print(f"Deduplicated votes: {len(deduplicated_votes)}")
    print(f"Votes removed: {votes_removed}")
    
    # Update the data
    data['votes'] = deduplicated_votes
    
    # Save the deduplicated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Deduplicated data saved!")

if __name__ == "__main__":
    find_and_fix_duplicates()
