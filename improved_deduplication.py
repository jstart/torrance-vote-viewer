#!/usr/bin/env python3
"""
Improved deduplication script that handles case sensitivity and other edge cases
"""

import json
from collections import defaultdict
import re

def normalize_agenda_item(agenda_item):
    """Normalize agenda item text for better matching"""
    if not agenda_item:
        return ""
    
    # Handle case where agenda_item is a dict
    if isinstance(agenda_item, dict):
        number = agenda_item.get('number', '')
        description = agenda_item.get('description', '')
        agenda_item = f"{number}. {description}".strip()
    
    # Convert to lowercase and strip whitespace
    normalized = agenda_item.lower().strip()
    
    # Remove common variations
    normalized = re.sub(r'\s+', ' ', normalized)  # Multiple spaces to single space
    
    # Handle common variations
    variations = {
        'consent calendar': 'consent calendar',
        'administrative matters': 'administrative matters',
        'hearings': 'hearings',
        'oral communications': 'oral communications',
        'adjournment': 'adjournment',
        'council committee meetings': 'council committee meetings'
    }
    
    for variation, standard in variations.items():
        if variation in normalized:
            normalized = standard
            break
    
    return normalized

def improved_deduplication():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print(f"Processing {len(data['votes'])} votes...")
    
    # Group votes by meeting_id and normalized agenda_item
    grouped_votes = defaultdict(list)
    
    for vote in data['votes']:
        meeting_id = vote.get('meeting_id', '')
        agenda_item = vote.get('agenda_item', '')
        normalized_agenda = normalize_agenda_item(agenda_item)
        key = f"{meeting_id}|{normalized_agenda}"
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
            meeting_id, normalized_agenda = key.split('|', 1)
            print(f"\nDeduplicating: {meeting_id}|{normalized_agenda}")
            
            # Show all votes being considered
            for i, vote in enumerate(votes):
                agenda_item = vote.get('agenda_item', '')
                result = vote.get('result', '')
                vote_tally = vote.get('vote_tally', {})
                vote_id = vote.get('id', '')
                print(f"  Vote {i+1}: '{agenda_item}' - {result} - {vote_tally} - ID: '{vote_id}'")
            
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
                
                # Prefer votes with more detailed vote tallies (including recusals, etc.)
                tally_keys = len(vote_tally.keys())
                score += tally_keys
                
                return score
            
            # Sort by quality score (highest first)
            votes.sort(key=vote_quality_score, reverse=True)
            best_vote = votes[0]
            
            # Use the most descriptive agenda item text
            agenda_items = [v.get('agenda_item', '') for v in votes if v.get('agenda_item')]
            if agenda_items:
                # Prefer longer, more descriptive agenda items
                best_agenda = max(agenda_items, key=len)
                best_vote['agenda_item'] = best_agenda
            
            deduplicated_votes.append(best_vote)
            votes_removed += len(votes) - 1
            
            print(f"  → Kept: '{best_vote.get('agenda_item', '')}' - {best_vote.get('result', 'Unknown')} - {best_vote.get('vote_tally', {})}")
            print(f"  → Removed: {len(votes) - 1} duplicate(s)")
    
    print(f"\n✅ Improved deduplication complete!")
    print(f"Original votes: {len(data['votes'])}")
    print(f"Deduplicated votes: {len(deduplicated_votes)}")
    print(f"Votes removed: {votes_removed}")
    
    # Update the data
    data['votes'] = deduplicated_votes
    
    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Improved deduplicated data saved!")

if __name__ == "__main__":
    improved_deduplication()
