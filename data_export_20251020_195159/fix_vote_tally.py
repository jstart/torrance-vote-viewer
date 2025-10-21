#!/usr/bin/env python3
"""
Fix vote_tally data by calculating from individual_votes
"""

import json
import sys

def fix_vote_tally_data():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print(f"Processing {len(data['votes'])} votes...")

    votes_fixed = 0

    for vote in data['votes']:
        # Check if vote_tally is empty or missing
        if not vote.get('vote_tally') or vote['vote_tally'] == {}:
            individual_votes = vote.get('individual_votes', {})

            if individual_votes:
                # Calculate vote tally from individual votes
                ayes = 0
                noes = 0
                abstentions = 0

                for councilmember, vote_result in individual_votes.items():
                    vote_result_upper = str(vote_result).upper()
                    if vote_result_upper in ['YES', 'Y', 'AYE']:
                        ayes += 1
                    elif vote_result_upper in ['NO', 'N', 'NAY']:
                        noes += 1
                    elif vote_result_upper in ['ABSTAIN', 'ABSTENTION']:
                        abstentions += 1

                # Update vote_tally
                vote['vote_tally'] = {
                    'ayes': ayes,
                    'noes': noes,
                    'abstentions': abstentions
                }

                # Update result based on vote tally
                if ayes > noes:
                    vote['result'] = 'Motion Passes'
                elif noes > ayes:
                    vote['result'] = 'Motion Fails'
                else:
                    vote['result'] = 'Tie'

                votes_fixed += 1
                print(f"Fixed vote {vote.get('id', 'unknown')}: {ayes} ayes, {noes} noes, {abstentions} abstentions")

    print(f"\n✅ Fixed {votes_fixed} votes with missing vote_tally data")

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("✅ Vote tally data fixed!")

if __name__ == "__main__":
    fix_vote_tally_data()
