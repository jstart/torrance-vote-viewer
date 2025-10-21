#!/usr/bin/env python3
"""
Parse raw vote data from 2025_meetings_data to extract individual votes
"""

import json
import os
import re
from collections import defaultdict

def parse_raw_vote_text(raw_text):
    """Parse raw text to extract individual votes"""
    if not raw_text:
        return {}

    individual_votes = {}

    # Look for councilmember vote patterns
    lines = raw_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Pattern: "councilmember name vote" - handle various vote formats
        match = re.match(r'councilmember\s+(\w+)\s+([a-z]+)', line.lower())
        if match:
            name = match.group(1)
            vote = match.group(2)

            # Handle OCR errors in vote results
            if vote in ['nl', 'ly', 'mal', 'mill', 'ai']:
                # These are likely OCR errors, try to map them to actual votes
                if vote in ['ly', 'y']:
                    vote = 'yea'
                elif vote in ['nl', 'n']:
                    vote = 'nay'
                elif vote in ['a', 'ai']:
                    vote = 'abstain'
                elif vote in ['mal', 'mill']:
                    # These are unclear, default to abstain
                    vote = 'abstain'
                else:
                    # Default to abstain for unclear votes
                    vote = 'abstain'

            # Normalize councilmember names
            if name == 'gerson':
                normalized_name = 'MIKE GERSON'
            elif name == 'kaji':
                normalized_name = 'JON KAJI'
            elif name == 'kalani':
                normalized_name = 'SHARON KALANI'
            elif name == 'lewis':
                normalized_name = 'BRIDGET LEWIS'
            elif name == 'mattucci':
                normalized_name = 'AURELIO MATTUCCI'
            elif name == 'sheikh':
                normalized_name = 'ASAM SHEIKH'
            elif name == 'chen':
                normalized_name = 'GEORGE CHEN'
            else:
                normalized_name = name.upper()

            # Normalize vote results
            if vote in ['yea', 'y', 'yes']:
                normalized_vote = 'YES'
            elif vote in ['nay', 'n', 'no', 'nl']:
                normalized_vote = 'NO'
            elif vote in ['abstain', 'a']:
                normalized_vote = 'ABSTAIN'
            else:
                normalized_vote = vote.upper()

            individual_votes[normalized_name] = normalized_vote

    return individual_votes

def extract_individual_votes_from_raw_data():
    # Path to the 2025 meetings data directory
    data_dir = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data"

    # Load the current consolidated data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        consolidated_data = json.load(f)

    print("Extracting individual vote data from raw text in 2025_meetings_data...")

    # Find all votable_vote_candidates files
    candidate_files = []
    for file in os.listdir(data_dir):
        if file.startswith('votable_vote_candidates_') and file.endswith('.json'):
            candidate_files.append(os.path.join(data_dir, file))

    print(f"Found {len(candidate_files)} votable_vote_candidates files")

    # Extract individual votes from each file
    raw_votes = defaultdict(dict)  # meeting_id -> frame_number -> individual_votes
    councilmember_names = set()

    for file_path in candidate_files:
        print(f"Processing {os.path.basename(file_path)}...")

        with open(file_path, 'r') as f:
            votes_data = json.load(f)

        for vote in votes_data:
            if vote.get('raw_text') and ('mattucci' in vote['raw_text'].lower() or 'lewis' in vote['raw_text'].lower()):
                meeting_id = vote['meeting_id']
                frame_number = vote['frame_number']
                raw_text = vote['raw_text']

                individual_votes = parse_raw_vote_text(raw_text)
                if individual_votes:
                    raw_votes[meeting_id][frame_number] = individual_votes
                    councilmember_names.update(individual_votes.keys())
                    print(f"  Found individual votes for {meeting_id}_{frame_number}: {list(individual_votes.keys())}")

    print(f"Found individual votes for {sum(len(frames) for frames in raw_votes.values())} votes")
    print(f"Councilmembers found: {sorted(councilmember_names)}")

    # Update the consolidated data with individual votes by matching frame numbers
    votes_updated = 0
    for vote in consolidated_data['votes']:
        meeting_id = vote['meeting_id']
        frame_number = vote['frame_number']

        # Try exact match first
        if meeting_id in raw_votes and frame_number in raw_votes[meeting_id]:
            vote['individual_votes'] = raw_votes[meeting_id][frame_number]
            votes_updated += 1
            print(f"Updated vote {vote['id']} with individual votes from raw text")
        else:
            # Try nearby frame numbers (within 5 frames)
            if meeting_id in raw_votes:
                for raw_frame, individual_votes in raw_votes[meeting_id].items():
                    if abs(raw_frame - frame_number) <= 5:
                        vote['individual_votes'] = individual_votes
                        votes_updated += 1
                        print(f"Updated vote {vote['id']} with individual votes from raw text (frame {raw_frame}, diff: {abs(raw_frame - frame_number)})")
                        break

    print(f"Updated {votes_updated} votes with individual vote data from raw text")

    # Update councilmembers list
    consolidated_data['councilmembers'] = sorted(councilmember_names)

    # Calculate councilmember stats
    councilmember_stats = {}
    for councilmember in councilmember_names:
        councilmember_stats[councilmember] = {
            'total_votes': 0,
            'yes_votes': 0,
            'no_votes': 0,
            'abstentions': 0
        }

    for vote in consolidated_data['votes']:
        if 'individual_votes' in vote:
            for councilmember, vote_result in vote['individual_votes'].items():
                if councilmember in councilmember_stats:
                    councilmember_stats[councilmember]['total_votes'] += 1
                    if vote_result == 'YES':
                        councilmember_stats[councilmember]['yes_votes'] += 1
                    elif vote_result == 'NO':
                        councilmember_stats[councilmember]['no_votes'] += 1
                    elif vote_result == 'ABSTAIN':
                        councilmember_stats[councilmember]['abstentions'] += 1

    consolidated_data['councilmember_stats'] = councilmember_stats

    # Create councilmember summaries
    councilmember_summaries = {}
    for councilmember in councilmember_names:
        stats = councilmember_stats[councilmember]
        councilmember_summaries[councilmember] = {
            'summary': f"{councilmember} serves as councilmember of the Torrance City Council. Participated in {stats['total_votes']} recorded votes with {stats['yes_votes']} yes votes and {stats['no_votes']} no votes.",
            'role': 'Councilmember' if 'MAYOR' not in councilmember else 'Mayor',
            'stats': stats
        }

    consolidated_data['councilmember_summaries'] = councilmember_summaries

    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(consolidated_data, f, indent=2)

    print("✅ Individual vote data extracted from raw text and merged successfully!")
    print(f"Updated councilmembers: {consolidated_data['councilmembers']}")

    # Print stats for each councilmember
    for councilmember in sorted(councilmember_names):
        stats = councilmember_stats[councilmember]
        print(f"{councilmember}: {stats['total_votes']} votes ({stats['yes_votes']} yes, {stats['no_votes']} no, {stats['abstentions']} abstain)")

if __name__ == "__main__":
    extract_individual_votes_from_raw_data()
