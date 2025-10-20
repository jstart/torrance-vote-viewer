#!/usr/bin/env python3
"""
Generate councilmember statistics and councilmembers array from vote data
"""

import json
import sys
from typing import Dict, List, Any

def update_councilmember_stats(votes: List[Dict]) -> Dict[str, Dict]:
    """Update councilmember statistics"""
    stats = {}

    for vote in votes:
        # Handle both VoteData objects and dictionaries
        if hasattr(vote, 'individual_votes'):
            # VoteData object
            individual_votes = vote.individual_votes or {}
        else:
            # Dictionary
            individual_votes = vote.get('individual_votes', {}) or {}

        # Ensure individual_votes is a dictionary, not a list
        if isinstance(individual_votes, list):
            individual_votes = {}

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

    return stats

def generate_councilmember_data(data_file: str):
    """Generate councilmember statistics and array from vote data"""
    print(f"🔧 Generating councilmember data for {data_file}...")

    # Load the data
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    votes = data.get('votes', [])
    print(f"📊 Processing {len(votes)} votes...")

    # Generate councilmember stats
    councilmember_stats = update_councilmember_stats(votes)

    # Generate councilmembers array from the stats
    councilmembers = list(councilmember_stats.keys())

    print(f"👥 Found {len(councilmembers)} councilmembers:")
    for cm in councilmembers:
        stats = councilmember_stats[cm]
        print(f"  {cm}: {stats['total_votes']} total votes ({stats['yes_votes']} yes, {stats['no_votes']} no, {stats['abstentions']} abstain)")

    # Update the data
    data['councilmember_stats'] = councilmember_stats
    data['councilmembers'] = councilmembers

    # Save the updated data
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Updated {data_file} with councilmember data")
    print(f"📄 Added {len(councilmembers)} councilmembers and their statistics")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_councilmember_stats.py <data_file>")
        sys.exit(1)

    data_file = sys.argv[1]
    generate_councilmember_data(data_file)
