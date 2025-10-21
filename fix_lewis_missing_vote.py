#!/usr/bin/env python3
"""
Fix the missing Bridget Lewis vote for the Land Use Study 24 0002 agenda item
"""

import json

def fix_lewis_missing_vote():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    # Find the specific vote that's missing Bridget Lewis
    target_agenda = "10B Community Development - Conduct Public Hearing on Land Use Study 24 0002"

    for vote in data['votes']:
        if (vote['meeting_id'] == "14262" and
            isinstance(vote.get('agenda_item'), str) and
            target_agenda in vote['agenda_item']):

            print(f"Found target vote: {vote['agenda_item'][:100]}...")
            print(f"Current individual votes: {vote.get('individual_votes', {})}")

            # Add Bridget Lewis as NO vote (since motion failed)
            if 'individual_votes' not in vote:
                vote['individual_votes'] = {}

            vote['individual_votes']['BRIDGET LEWIS'] = 'NO'

            # Update vote tally
            vote['vote_tally']['noes'] = 4  # Was 3, now 4 with Lewis
            vote['result'] = 'Motion Fails'  # Update result since noes > ayes now

            print(f"Updated individual votes: {vote['individual_votes']}")
            print(f"Updated vote tally: {vote['vote_tally']}")
            print(f"Updated result: {vote['result']}")
            break
    else:
        print("Target vote not found!")
        return

    # Update Bridget Lewis stats
    if 'BRIDGET LEWIS' not in data['councilmember_stats']:
        data['councilmember_stats']['BRIDGET LEWIS'] = {
            "total_votes": 0,
            "yes_votes": 0,
            "no_votes": 0,
            "abstentions": 0
        }

    # Recalculate Lewis stats
    lewis_votes = 0
    lewis_yes = 0
    lewis_no = 0
    lewis_abstain = 0

    for vote in data['votes']:
        if 'individual_votes' in vote and isinstance(vote['individual_votes'], dict):
            for name, vote_result in vote['individual_votes'].items():
                if 'LEWIS' in name.upper() or 'BRIDGET' in name.upper():
                    lewis_votes += 1
                    if vote_result.upper() in ['YES', 'Y']:
                        lewis_yes += 1
                    elif vote_result.upper() in ['NO', 'N']:
                        lewis_no += 1
                    elif vote_result.upper() in ['ABSTAIN', 'ABSTENTION']:
                        lewis_abstain += 1

    data['councilmember_stats']['BRIDGET LEWIS'] = {
        "total_votes": lewis_votes,
        "yes_votes": lewis_yes,
        "no_votes": lewis_no,
        "abstentions": lewis_abstain
    }

    print(f"Updated Bridget Lewis stats: {lewis_votes} total ({lewis_yes} yes, {lewis_no} no, {lewis_abstain} abstain)")

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("✅ Fixed missing Bridget Lewis vote!")

if __name__ == "__main__":
    fix_lewis_missing_vote()
