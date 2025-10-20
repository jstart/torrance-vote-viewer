#!/usr/bin/env python3
"""
Script to restore individual vote data from the original vote files
and merge it with our consolidated data.
"""

import json
import os
from collections import defaultdict

def load_individual_votes():
    """Load individual vote data from all votable_votes files."""
    source_dir = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data"

    individual_votes_by_meeting = defaultdict(list)
    all_councilmember_names = set()

    print("🔍 Loading individual vote data...")

    # Process all votable_votes files
    for file_name in os.listdir(source_dir):
        if file_name.startswith('votable_votes_') and file_name.endswith('.json'):
            file_path = os.path.join(source_dir, file_name)

            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                if isinstance(data, list):
                    votes_with_council = 0
                    for vote in data:
                        if 'council_member_votes' in vote and vote['council_member_votes']:
                            votes_with_council += 1

                            # Extract meeting ID
                            meeting_id = vote.get('meeting_id')
                            if not meeting_id:
                                continue

                            # Process council member votes
                            council_votes = vote['council_member_votes']
                            if isinstance(council_votes, list):
                                individual_votes = []
                                for cv in council_votes:
                                    if isinstance(cv, dict) and 'name' in cv and 'vote' in cv:
                                        name = cv['name']
                                        vote_result = cv['vote']

                                        # Normalize names
                                        if name.startswith('Councilmember '):
                                            name = name.replace('Councilmember ', '')
                                        elif name.startswith('Mayor '):
                                            name = name.replace('Mayor ', '')

                                        all_councilmember_names.add(name)

                                        # Normalize vote results
                                        normalized_result = vote_result.upper()
                                        if normalized_result in ['Y', 'YEA', 'YES']:
                                            normalized_result = 'Y'
                                        elif normalized_result in ['N', 'NAY', 'NO']:
                                            normalized_result = 'N'
                                        elif normalized_result in ['A', 'ABSTAIN', 'ABSTENTION']:
                                            normalized_result = 'A'

                                        individual_votes.append({
                                            'name': name,
                                            'result': normalized_result
                                        })

                                # Create vote record with individual votes
                                vote_record = {
                                    'meeting_id': meeting_id,
                                    'agenda_item': vote.get('agenda_item'),
                                    'motion_text': vote.get('motion_text'),
                                    'vote_tally': vote.get('vote_tally'),
                                    'result': vote.get('result'),
                                    'individual_votes': individual_votes,
                                    'frame_number': vote.get('frame_number'),
                                    'confidence': vote.get('confidence')
                                }

                                individual_votes_by_meeting[meeting_id].append(vote_record)

                if votes_with_council > 0:
                    print(f"✅ {file_name}: {votes_with_council} votes with individual data")

            except Exception as e:
                print(f"⚠️ Error reading {file_name}: {e}")

    print(f"\n📊 Summary:")
    print(f"Meetings with individual vote data: {len(individual_votes_by_meeting)}")
    print(f"Total votes with individual data: {sum(len(votes) for votes in individual_votes_by_meeting.values())}")
    print(f"Councilmember names: {sorted(list(all_councilmember_names))}")

    return individual_votes_by_meeting, all_councilmember_names

def merge_with_existing_data():
    """Merge individual vote data with existing consolidated data."""

    # Load existing consolidated data
    with open('data/torrance_votes_consolidated_final.json', 'r') as f:
        existing_data = json.load(f)

    print(f"\n📁 Existing data: {len(existing_data.get('votes', []))} votes")

    # Load individual vote data
    individual_votes_by_meeting, councilmember_names = load_individual_votes()

    # Create mapping from meeting_id to individual votes
    individual_votes_map = {}
    for meeting_id, votes in individual_votes_by_meeting.items():
        for vote in votes:
            # Create a key based on meeting_id and agenda_item
            key = f"{meeting_id}_{vote.get('agenda_item', 'unknown')}"
            individual_votes_map[key] = vote['individual_votes']

    print(f"\n🔗 Mapping {len(individual_votes_map)} individual vote records to existing votes...")

    # Merge individual votes into existing data
    merged_votes = []
    matched_count = 0

    for vote in existing_data.get('votes', []):
        meeting_id = vote.get('meeting_id')
        agenda_item = vote.get('agenda_item')

        # Try to find matching individual votes
        key = f"{meeting_id}_{agenda_item}"
        if key in individual_votes_map:
            vote['individual_votes'] = individual_votes_map[key]
            matched_count += 1
        else:
            # Try alternative keys
            alt_key = f"{meeting_id}_unknown"
            if alt_key in individual_votes_map:
                vote['individual_votes'] = individual_votes_map[alt_key]
                matched_count += 1
            else:
                vote['individual_votes'] = None

        merged_votes.append(vote)

    print(f"✅ Matched {matched_count} votes with individual vote data")

    # Update the data structure
    existing_data['votes'] = merged_votes

    # Add councilmember information
    existing_data['councilmembers'] = sorted(list(councilmember_names))

    # Calculate councilmember statistics
    councilmember_stats = {}
    for name in councilmember_names:
        total_votes = 0
        yes_votes = 0
        no_votes = 0

        for vote in merged_votes:
            if vote.get('individual_votes'):
                for individual_vote in vote['individual_votes']:
                    if individual_vote.get('name') == name:
                        total_votes += 1
                        result = individual_vote.get('result', '').upper()
                        if result == 'Y':
                            yes_votes += 1
                        elif result == 'N':
                            no_votes += 1

        councilmember_stats[name] = {
            'total_votes': total_votes,
            'yes_votes': yes_votes,
            'no_votes': no_votes
        }

    existing_data['councilmember_stats'] = councilmember_stats

    # Save the merged data
    output_file = 'data/torrance_votes_with_individual_votes.json'
    with open(output_file, 'w') as f:
        json.dump(existing_data, f, indent=2)

    print(f"\n💾 Saved merged data to {output_file}")
    print(f"📊 Final stats:")
    print(f"  Total votes: {len(merged_votes)}")
    print(f"  Votes with individual data: {matched_count}")
    print(f"  Councilmembers: {len(councilmember_names)}")

    return output_file

if __name__ == "__main__":
    merge_with_existing_data()
