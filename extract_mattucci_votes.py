#!/usr/bin/env python3
"""
Extract Aurelio Mattucci's vote data from raw files
"""

import json
import os
import re
from collections import defaultdict

def extract_mattucci_votes():
    # Path to the 2025 meetings data directory
    data_dir = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data"

    # Load the current consolidated data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        consolidated_data = json.load(f)

    print("Extracting Aurelio Mattucci's vote data from raw files...")

    # Find all votable_vote_candidates files
    candidate_files = []
    for file in os.listdir(data_dir):
        if file.startswith('votable_vote_candidates_') and file.endswith('.json'):
            candidate_files.append(os.path.join(data_dir, file))

    print(f"Found {len(candidate_files)} votable_vote_candidates files")

    # Extract Mattucci votes from each file
    mattucci_votes = defaultdict(dict)  # meeting_id -> frame_number -> vote_result
    votes_found = 0

    for file_path in candidate_files:
        print(f"Processing {os.path.basename(file_path)}...")

        with open(file_path, 'r') as f:
            votes_data = json.load(f)

        for vote in votes_data:
            if vote.get('raw_text') and 'mattucci' in vote['raw_text'].lower():
                meeting_id = vote['meeting_id']
                frame_number = vote['frame_number']
                raw_text = vote['raw_text']

                # Parse Mattucci's vote from raw text
                mattucci_vote = parse_mattucci_vote(raw_text)
                if mattucci_vote:
                    mattucci_votes[meeting_id][frame_number] = mattucci_vote
                    votes_found += 1
                    print(f"  Found Mattucci vote in {meeting_id}_{frame_number}: {mattucci_vote}")

    print(f"\nFound {votes_found} Mattucci votes across {len(mattucci_votes)} meetings")

    # Update the consolidated data with Mattucci's votes
    votes_updated = 0
    for vote in consolidated_data['votes']:
        meeting_id = vote['meeting_id']
        frame_number = vote.get('frame_number')

        if meeting_id in mattucci_votes and frame_number in mattucci_votes[meeting_id]:
            # Add Mattucci to individual_votes if not present
            if 'individual_votes' not in vote:
                vote['individual_votes'] = {}

            vote['individual_votes']['AURELIO MATTUCCI'] = mattucci_votes[meeting_id][frame_number]
            votes_updated += 1
            print(f"Updated vote {vote.get('id', 'unknown')} with Mattucci's vote: {mattucci_votes[meeting_id][frame_number]}")

    # Recalculate Mattucci's stats
    mattucci_total = 0
    mattucci_yes = 0
    mattucci_no = 0
    mattucci_abstain = 0

    for vote in consolidated_data['votes']:
        if 'individual_votes' in vote and 'AURELIO MATTUCCI' in vote['individual_votes']:
            mattucci_total += 1
            vote_result = vote['individual_votes']['AURELIO MATTUCCI']
            if vote_result == 'YES':
                mattucci_yes += 1
            elif vote_result == 'NO':
                mattucci_no += 1
            elif vote_result == 'ABSTAIN':
                mattucci_abstain += 1

    # Update Mattucci's stats
    consolidated_data['councilmember_stats']['AURELIO MATTUCCI'] = {
        "total_votes": mattucci_total,
        "yes_votes": mattucci_yes,
        "no_votes": mattucci_no,
        "abstentions": mattucci_abstain
    }

    # Update Mattucci's summary
    consolidated_data['councilmember_summaries']['AURELIO MATTUCCI']['notes'] = [
        f"Participated in {mattucci_total} recorded votes",
        f"Voted Yes on {mattucci_yes} motions",
        f"Voted No on {mattucci_no} motions",
        f"Active in {len(set(vote.get('agenda_item', '') for vote in consolidated_data['votes'] if 'individual_votes' in vote and 'AURELIO MATTUCCI' in vote['individual_votes']))} policy areas"
    ]

    consolidated_data['councilmember_summaries']['AURELIO MATTUCCI']['stats'] = {
        "total_votes": mattucci_total,
        "yes_votes": mattucci_yes,
        "no_votes": mattucci_no
    }

    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(consolidated_data, f, indent=2)

    print(f"\n✅ Updated {votes_updated} votes with Mattucci's vote data!")
    print(f"📊 Mattucci stats: {mattucci_total} total ({mattucci_yes} yes, {mattucci_no} no, {mattucci_abstain} abstain)")

def parse_mattucci_vote(raw_text):
    """Parse Mattucci's vote from raw text"""
    lines = raw_text.split('\n')

    for line in lines:
        line = line.strip().lower()
        if 'mattucci' in line:
            # Extract the vote result after "mattucci"
            parts = line.split('mattucci')
            if len(parts) > 1:
                vote_part = parts[1].strip()

                # Map common OCR errors to actual votes
                if vote_part in ['nil', 'nl', 'n']:
                    return 'NO'
                elif vote_part in ['yea', 'y', 'yes']:
                    return 'YES'
                elif vote_part in ['aa', 'abstain', 'a']:
                    return 'ABSTAIN'
                elif vote_part in ['ra', 'r']:
                    return 'YES'  # "ra" likely means "yea"
                elif vote_part in ['na', 'nay']:
                    return 'NO'
                elif vote_part in ['am']:
                    return 'ABSTAIN'  # "am" likely means "abstain"
                else:
                    # Default to abstain for unclear votes
                    return 'ABSTAIN'

    return None

if __name__ == "__main__":
    extract_mattucci_votes()
