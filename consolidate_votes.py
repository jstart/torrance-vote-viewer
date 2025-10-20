#!/usr/bin/env python3
"""
Script to consolidate duplicate votes and fix the data structure.
This will merge votes with the same agenda item and preserve individual vote data.
"""

import json
from collections import defaultdict

def consolidate_votes():
    """Consolidate duplicate votes by agenda item."""
    
    # Load the enhanced data (which has individual_votes)
    with open('data/torrance_votes_enhanced.json', 'r') as f:
        enhanced_data = json.load(f)
    
    # Load the current consolidated data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        consolidated_data = json.load(f)
    
    enhanced_votes = enhanced_data.get('votes', [])
    consolidated_votes = consolidated_data.get('votes', [])
    
    print(f"🔍 Processing votes...")
    print(f"Enhanced votes: {len(enhanced_votes)}")
    print(f"Consolidated votes: {len(consolidated_votes)}")
    print()
    
    # Group enhanced votes by meeting_id and agenda_item
    grouped_votes = defaultdict(list)
    
    for vote in enhanced_votes:
        meeting_id = vote.get('meeting_id')
        agenda_item = vote.get('agenda_item', '')
        key = f"{meeting_id}_{agenda_item}"
        grouped_votes[key].append(vote)
    
    print(f"Grouped votes into {len(grouped_votes)} unique agenda items")
    print()
    
    # Create consolidated votes
    new_votes = []
    
    for key, votes_group in grouped_votes.items():
        if len(votes_group) == 1:
            # Single vote, use as-is
            consolidated_vote = votes_group[0].copy()
        else:
            # Multiple votes, consolidate them
            print(f"Consolidating {len(votes_group)} votes for: {votes_group[0].get('agenda_item', '')[:50]}...")
            
            # Use the first vote as base
            consolidated_vote = votes_group[0].copy()
            
            # Merge individual votes
            all_individual_votes = []
            for vote in votes_group:
                if vote.get('individual_votes'):
                    all_individual_votes.extend(vote['individual_votes'])
            
            if all_individual_votes:
                consolidated_vote['individual_votes'] = all_individual_votes
                
                # Calculate consolidated vote tally
                ayes = sum(1 for v in all_individual_votes if v.get('vote', '').lower() in ['yes', 'aye'])
                noes = sum(1 for v in all_individual_votes if v.get('vote', '').lower() in ['no', 'nay'])
                abstentions = sum(1 for v in all_individual_votes if v.get('vote', '').lower() in ['abstain', 'abstention'])
                
                consolidated_vote['vote_tally'] = {
                    'ayes': ayes,
                    'noes': noes,
                    'abstentions': abstentions
                }
                
                # Determine result
                if ayes > noes:
                    consolidated_vote['result'] = 'Passes'
                elif noes > ayes:
                    consolidated_vote['result'] = 'Fails'
                else:
                    consolidated_vote['result'] = 'Tie'
            
            # Use the earliest frame number
            frame_numbers = [v.get('frame_number', 0) for v in votes_group if v.get('frame_number')]
            if frame_numbers:
                consolidated_vote['frame_number'] = min(frame_numbers)
            
            # Use the earliest video timestamp
            timestamps = [v.get('video_timestamp') for v in votes_group if v.get('video_timestamp')]
            if timestamps:
                consolidated_vote['video_timestamp'] = min(timestamps)
        
        new_votes.append(consolidated_vote)
    
    print(f"\n📊 Consolidation Results:")
    print(f"Original votes: {len(enhanced_votes)}")
    print(f"Consolidated votes: {len(new_votes)}")
    print(f"Reduction: {len(enhanced_votes) - len(new_votes)} votes")
    print()
    
    # Update the consolidated data
    consolidated_data['votes'] = new_votes
    
    # Update metadata
    consolidated_data['metadata']['total_votes'] = len(new_votes)
    
    # Recalculate meeting statistics
    meetings = consolidated_data.get('meetings', {})
    for meeting_id, meeting in meetings.items():
        meeting_votes = [v for v in new_votes if v.get('meeting_id') == meeting_id]
        meeting['total_votes'] = len(meeting_votes)
        
        # Calculate vote results
        passed = sum(1 for v in meeting_votes if v.get('result', '').lower().startswith('pass'))
        failed = sum(1 for v in meeting_votes if v.get('result', '').lower().startswith('fail'))
        
        meeting['vote_results'] = {
            'passed': passed,
            'failed': failed
        }
    
    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(consolidated_data, f, indent=2)
    
    print("✅ Consolidated data saved!")
    
    # Verify the results
    meeting_14490_votes = [v for v in new_votes if v.get('meeting_id') == '14490']
    print(f"\n🔍 Verification for meeting 14490:")
    print(f"Votes: {len(meeting_14490_votes)}")
    
    votes_with_individual = [v for v in meeting_14490_votes if v.get('individual_votes')]
    print(f"Votes with individual_votes: {len(votes_with_individual)}")
    
    if votes_with_individual:
        print("✅ Individual votes preserved!")
    else:
        print("❌ Individual votes still missing!")

if __name__ == "__main__":
    consolidate_votes()
