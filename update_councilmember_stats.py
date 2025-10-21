#!/usr/bin/env python3
"""
Update councilmember stats after fixing Mattucci's votes
"""

import json

def update_councilmember_stats():
    """Recalculate councilmember stats after fixing Mattucci's votes"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("🔄 Updating councilmember stats...")
    
    # Recalculate stats for all councilmembers
    stats = {}
    
    for vote in data.get('votes', []):
        individual_votes = vote.get('individual_votes', {})
        
        for councilmember, vote_choice in individual_votes.items():
            if councilmember not in stats:
                stats[councilmember] = {
                    'total_votes': 0,
                    'yes_votes': 0,
                    'no_votes': 0,
                    'abstentions': 0
                }
            
            stats[councilmember]['total_votes'] += 1
            
            if vote_choice.upper() == 'YES':
                stats[councilmember]['yes_votes'] += 1
            elif vote_choice.upper() == 'NO':
                stats[councilmember]['no_votes'] += 1
            elif vote_choice.upper() == 'ABSTAIN':
                stats[councilmember]['abstentions'] += 1
    
    # Update the data
    data['councilmember_stats'] = stats
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Updated councilmember stats")
    
    # Show Mattucci's updated stats
    mattucci_stats = stats.get('AURELIO MATTUCCI', {})
    print(f"\n📊 Mattucci's Updated Stats:")
    print(f"   - Total votes: {mattucci_stats.get('total_votes', 0)}")
    print(f"   - YES votes: {mattucci_stats.get('yes_votes', 0)}")
    print(f"   - NO votes: {mattucci_stats.get('no_votes', 0)}")
    print(f"   - ABSTAIN votes: {mattucci_stats.get('abstentions', 0)}")

if __name__ == "__main__":
    update_councilmember_stats()
