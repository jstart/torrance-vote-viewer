#!/usr/bin/env python3
"""
Check 2024 meetings for missing Bridget Lewis votes
"""

import json

def check_2024_lewis_votes():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    # Find all 2024 meetings
    votes_2024 = [vote for vote in data['votes'] if vote.get('meeting_id', '').startswith('142')]

    print(f"Found {len(votes_2024)} votes from 2024 meetings")

    # Check which ones are missing Bridget Lewis
    missing_lewis = []
    has_lewis = []

    for vote in votes_2024:
        meeting_id = vote.get('meeting_id', '')
        individual_votes = vote.get('individual_votes', {})

        if isinstance(individual_votes, dict):
            if 'BRIDGET LEWIS' in individual_votes:
                has_lewis.append(vote)
            else:
                missing_lewis.append(vote)
        else:
            print(f"Warning: Vote {vote.get('id', 'unknown')} has non-dict individual_votes: {type(individual_votes)}")

    print(f"\n2024 votes WITH Bridget Lewis: {len(has_lewis)}")
    print(f"2024 votes MISSING Bridget Lewis: {len(missing_lewis)}")

    if missing_lewis:
        print(f"\nMissing Bridget Lewis from these 2024 votes:")
        for vote in missing_lewis[:10]:  # Show first 10
            agenda = vote.get('agenda_item', 'Unknown')
            if isinstance(agenda, str):
                agenda = agenda[:60] + "..." if len(agenda) > 60 else agenda
            print(f"  - Meeting {vote.get('meeting_id')}: {agenda}")

        if len(missing_lewis) > 10:
            print(f"  ... and {len(missing_lewis) - 10} more")

    # Check which 2024 meetings have votes
    meetings_2024 = set(vote.get('meeting_id') for vote in votes_2024)
    print(f"\n2024 meetings with votes: {sorted(meetings_2024)}")

    # Check if Bridget Lewis should be in 2024 meetings
    # Based on the pattern, she should be in most 2024 meetings too
    print(f"\nShould Bridget Lewis be in 2024 meetings?")
    print(f"Based on the data pattern, she should be present in most 2024 meetings.")
    print(f"Currently missing from {len(missing_lewis)} out of {len(votes_2024)} 2024 votes.")

if __name__ == "__main__":
    check_2024_lewis_votes()
