#!/usr/bin/env python3
"""
Merge individual vote data from 2025_meetings_data by matching agenda items
"""

import json
import os
from collections import defaultdict

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
    # Remove common prefixes/suffixes that don't affect meaning
    normalized = re.sub(r'^(item\s+\d+\s*:\s*)', '', normalized)
    normalized = re.sub(r'^(no\.\s*\d+\s*)', '', normalized)
    normalized = re.sub(r'\s*\(for adoption only\)\s*$', '', normalized)
    normalized = re.sub(r'\s*\(for presentation\)\s*$', '', normalized)
    normalized = re.sub(r'\s*\(for discussion\)\s*$', '', normalized)
    normalized = re.sub(r'\s*expenditure:\s*none\.?\s*$', '', normalized)
    normalized = re.sub(r'\s*expenditure:\s*\$[0-9,]+\.?\s*$', '', normalized)

    return normalized

def extract_individual_votes_from_2025_data():
    # Path to the 2025 meetings data directory
    data_dir = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data"

    # Load the current consolidated data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        consolidated_data = json.load(f)

    print("Extracting individual vote data from 2025_meetings_data by agenda item matching...")

    # Find all votable_votes files
    votable_files = []
    for file in os.listdir(data_dir):
        if file.startswith('votable_votes_') and file.endswith('.json'):
            votable_files.append(os.path.join(data_dir, file))

    print(f"Found {len(votable_files)} votable_votes files")

    # Extract individual votes from each file, organized by meeting_id and agenda_item
    agenda_votes = defaultdict(dict)  # meeting_id -> agenda_item -> individual_votes
    councilmember_names = set()

    for file_path in votable_files:
        print(f"Processing {os.path.basename(file_path)}...")

        with open(file_path, 'r') as f:
            votes_data = json.load(f)

        for vote in votes_data:
            if vote.get('individual_votes'):
                meeting_id = vote['meeting_id']
                agenda_item = vote.get('agenda_item', '')
                normalized_agenda = normalize_agenda_item(agenda_item)

                individual_votes = {}

                for councilmember_vote in vote['individual_votes']:
                    if isinstance(councilmember_vote, dict):
                        councilmember_name = councilmember_vote.get('council_member', '')
                        vote_result = councilmember_vote.get('vote', '')
                    else:
                        print(f"Unexpected individual_vote structure: {councilmember_vote}")
                        continue

                    # Normalize councilmember names
                    if 'Mayor' in councilmember_name:
                        normalized_name = 'GEORGE CHEN'
                    elif 'Gerson' in councilmember_name:
                        normalized_name = 'MIKE GERSON'
                    elif 'Kaji' in councilmember_name:
                        normalized_name = 'JON KAJI'
                    elif 'Kalani' in councilmember_name:
                        normalized_name = 'SHARON KALANI'
                    elif 'Lewis' in councilmember_name:
                        normalized_name = 'BRIDGET LEWIS'
                    elif 'Mattucci' in councilmember_name:
                        normalized_name = 'AURELIO MATTUCCI'
                    elif 'Sheikh' in councilmember_name:
                        normalized_name = 'ASAM SHAIKH'
                    else:
                        normalized_name = councilmember_name.upper()

                    # Normalize vote results
                    if vote_result.upper() in ['Y', 'YES', 'AYE', 'YEA']:
                        normalized_vote = 'YES'
                    elif vote_result.upper() in ['N', 'NO', 'NAY', 'NAY!']:
                        normalized_vote = 'NO'
                    elif vote_result.upper() in ['A', 'ABSTAIN', 'ABSTENTION']:
                        normalized_vote = 'ABSTAIN'
                    else:
                        normalized_vote = vote_result.upper()

                    individual_votes[normalized_name] = normalized_vote
                    councilmember_names.add(normalized_name)

                if individual_votes:
                    agenda_votes[meeting_id][normalized_agenda] = individual_votes

    print(f"Found individual votes for {sum(len(agendas) for agendas in agenda_votes.values())} agenda items")
    print(f"Councilmembers found: {sorted(councilmember_names)}")

    # Update the consolidated data with individual votes by matching agenda items
    votes_updated = 0
    for vote in consolidated_data['votes']:
        meeting_id = vote['meeting_id']
        agenda_item = vote.get('agenda_item', '')
        normalized_agenda = normalize_agenda_item(agenda_item)

        # Try exact match first
        if meeting_id in agenda_votes and normalized_agenda in agenda_votes[meeting_id]:
            vote['individual_votes'] = agenda_votes[meeting_id][normalized_agenda]
            votes_updated += 1
            print(f"Updated vote {vote['id']} with individual votes for agenda: {normalized_agenda}")
        else:
            # Try partial match by agenda item number (e.g., "10A" matches "10A. ...")
            if isinstance(agenda_item, str) and '.' in agenda_item:
                agenda_number = agenda_item.split('.')[0].strip()
                if meeting_id in agenda_votes:
                    for agenda_key, individual_votes in agenda_votes[meeting_id].items():
                        if agenda_key.startswith(agenda_number.lower()):
                            vote['individual_votes'] = individual_votes
                            votes_updated += 1
                            print(f"Updated vote {vote['id']} with individual votes for agenda: {agenda_key} (partial match)")
                            break

    print(f"Updated {votes_updated} votes with individual vote data")

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

    print("✅ Individual vote data extracted and merged successfully!")
    print(f"Updated councilmembers: {consolidated_data['councilmembers']}")

    # Print stats for each councilmember
    for councilmember in sorted(councilmember_names):
        stats = councilmember_stats[councilmember]
        print(f"{councilmember}: {stats['total_votes']} votes ({stats['yes_votes']} yes, {stats['no_votes']} no, {stats['abstentions']} abstain)")

if __name__ == "__main__":
    import re
    extract_individual_votes_from_2025_data()
