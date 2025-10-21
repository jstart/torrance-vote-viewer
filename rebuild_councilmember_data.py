#!/usr/bin/env python3
"""
Rebuild councilmember data from votes
"""

import json
from collections import defaultdict

def rebuild_councilmember_data():
    """Rebuild councilmember data from individual votes"""
    
    # Load current data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("Rebuilding councilmember data from votes...")
    
    # Extract unique councilmember names from votes
    councilmember_names = set()
    councilmember_stats = defaultdict(lambda: {
        'total_votes': 0,
        'yes_votes': 0,
        'no_votes': 0,
        'abstentions': 0
    })
    
    # Process all votes
    for vote in data.get('votes', []):
        individual_votes = vote.get('individual_votes', {})
        
        if isinstance(individual_votes, dict):
            for councilmember, vote_choice in individual_votes.items():
                councilmember_names.add(councilmember)
                
                # Update stats
                stats = councilmember_stats[councilmember]
                stats['total_votes'] += 1
                
                if vote_choice.upper() == 'YES':
                    stats['yes_votes'] += 1
                elif vote_choice.upper() == 'NO':
                    stats['no_votes'] += 1
                elif vote_choice.upper() == 'ABSTAIN':
                    stats['abstentions'] += 1
    
    # Convert to regular dict and sort
    councilmember_stats = dict(councilmember_stats)
    
    # Create councilmembers array (sorted alphabetically)
    councilmembers = sorted(list(councilmember_names))
    
    print(f"Found {len(councilmembers)} councilmembers:")
    for name in councilmembers:
        stats = councilmember_stats[name]
        print(f"  {name}: {stats['total_votes']} votes ({stats['yes_votes']} yes, {stats['no_votes']} no, {stats['abstentions']} abstain)")
    
    # Update the data
    data['councilmembers'] = councilmembers
    data['councilmember_stats'] = councilmember_stats
    
    # Create basic summaries if they don't exist
    if 'councilmember_summaries' not in data or not data['councilmember_summaries']:
        data['councilmember_summaries'] = {}
        for name in councilmembers:
            stats = councilmember_stats[name]
            data['councilmember_summaries'][name] = {
                'summary': f"{name} has participated in {stats['total_votes']} votes, with {stats['yes_votes']} yes votes, {stats['no_votes']} no votes, and {stats['abstentions']} abstentions.",
                'bio_url': f"https://www.torranceca.gov/government/city-council-and-elected-officials/{name.lower().replace(' ', '-')}"
            }
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✅ Rebuilt councilmember data!")
    print(f"📊 Results:")
    print(f"   - Councilmembers: {len(councilmembers)}")
    print(f"   - Stats entries: {len(councilmember_stats)}")
    print(f"   - Summaries: {len(data['councilmember_summaries'])}")

if __name__ == "__main__":
    rebuild_councilmember_data()
