#!/usr/bin/env python3
"""
Fix duplicate ASAM SHAIKH/SHEIKH entries and consolidate councilmember data
"""

import json

def fix_duplicate_councilmembers():
    """Fix duplicate ASAM SHAIKH/SHEIKH entries"""
    
    # Load current data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("Fixing duplicate ASAM SHAIKH/SHEIKH entries...")
    
    # Consolidate ASAM SHAIKH and ASAM SHEIKH
    if 'ASAM SHAIKH' in data['councilmember_stats'] and 'ASAM SHEIKH' in data['councilmember_stats']:
        # Merge stats
        shaikh_stats = data['councilmember_stats']['ASAM SHAIKH']
        sheikh_stats = data['councilmember_stats']['ASAM SHEIKH']
        
        consolidated_stats = {
            'total_votes': shaikh_stats['total_votes'] + sheikh_stats['total_votes'],
            'yes_votes': shaikh_stats['yes_votes'] + sheikh_stats['yes_votes'],
            'no_votes': shaikh_stats['no_votes'] + sheikh_stats['no_votes'],
            'abstentions': shaikh_stats['abstentions'] + sheikh_stats['abstentions']
        }
        
        # Use ASAM SHEIKH as the canonical name
        data['councilmember_stats']['ASAM SHEIKH'] = consolidated_stats
        del data['councilmember_stats']['ASAM SHAIKH']
        
        # Update councilmembers array
        data['councilmembers'] = [name for name in data['councilmembers'] if name != 'ASAM SHAIKH']
        
        # Update summaries
        if 'ASAM SHAIKH' in data['councilmember_summaries']:
            del data['councilmember_summaries']['ASAM SHAIKH']
        
        # Update individual votes
        for vote in data['votes']:
            if 'individual_votes' in vote and isinstance(vote['individual_votes'], dict):
                if 'ASAM SHAIKH' in vote['individual_votes']:
                    vote['individual_votes']['ASAM SHEIKH'] = vote['individual_votes']['ASAM SHAIKH']
                    del vote['individual_votes']['ASAM SHAIKH']
        
        print(f"  Consolidated ASAM SHAIKH into ASAM SHEIKH")
        print(f"  Total votes: {consolidated_stats['total_votes']}")
    
    # Ensure we have the right councilmembers (remove any that shouldn't be there)
    expected_councilmembers = [
        "GEORGE CHEN",
        "MIKE GERSON", 
        "JON KAJI",
        "SHARON KALANI",
        "ASAM SHEIKH",
        "AURELIO MATTUCCI",
        "BRIDGET LEWIS"
    ]
    
    # Update councilmembers array
    data['councilmembers'] = expected_councilmembers
    
    # Ensure all expected councilmembers have stats
    for name in expected_councilmembers:
        if name not in data['councilmember_stats']:
            data['councilmember_stats'][name] = {
                'total_votes': 0,
                'yes_votes': 0,
                'no_votes': 0,
                'abstentions': 0
            }
    
    # Remove any extra councilmembers from stats
    stats_to_remove = [name for name in data['councilmember_stats'] if name not in expected_councilmembers]
    for name in stats_to_remove:
        del data['councilmember_stats'][name]
        print(f"  Removed {name} from stats")
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✅ Fixed councilmember data!")
    print(f"📊 Final councilmembers: {data['councilmembers']}")

if __name__ == "__main__":
    fix_duplicate_councilmembers()
