#!/usr/bin/env python3
"""
Use Gemini AI to parse individual votes from raw text data
"""

import json
import os
import google.generativeai as genai
from collections import defaultdict

# Configure Gemini API
genai.configure(api_key="AIzaSyBvOkBwJcTTTMc8yD13D8awxWg5U_OPYrU")
model = genai.GenerativeModel('gemini-1.5-flash')

def parse_votes_with_gemini(raw_text):
    """Use Gemini to parse individual votes from raw text"""
    if not raw_text:
        return {}

    prompt = f"""
    Analyze this raw text from a city council meeting vote and extract the individual councilmember votes.

    Raw text:
    {raw_text}

    Please return ONLY a JSON object with the councilmember names as keys and their votes as values.
    Use these exact councilmember names: MIKE GERSON, JON KAJI, SHARON KALANI, BRIDGET LEWIS, AURELIO MATTUCCI, ASAM SHEIKH
    Use these exact vote values: YES, NO, ABSTAIN

    If a councilmember is not present in the text, do not include them in the result.
    If the vote is unclear, use ABSTAIN.

    Example format:
    {{
        "MIKE GERSON": "YES",
        "JON KAJI": "NO",
        "SHARON KALANI": "ABSTAIN"
    }}

    Return only the JSON, no other text.
    """

    try:
        response = model.generate_content(prompt)
        result_text = response.text.strip()

        # Clean up the response to extract JSON
        if result_text.startswith('```json'):
            result_text = result_text[7:]
        if result_text.endswith('```'):
            result_text = result_text[:-3]
        if result_text.startswith('```'):
            result_text = result_text[3:]

        result_text = result_text.strip()

        # Parse JSON
        votes = json.loads(result_text)

        # Validate and normalize the votes
        valid_votes = {}
        for name, vote in votes.items():
            if name.upper() in ['MIKE GERSON', 'JON KAJI', 'SHARON KALANI', 'BRIDGET LEWIS', 'AURELIO MATTUCCI', 'ASAM SHEIKH']:
                vote_upper = vote.upper()
                if vote_upper in ['YES', 'NO', 'ABSTAIN']:
                    valid_votes[name.upper()] = vote_upper
                else:
                    valid_votes[name.upper()] = 'ABSTAIN'

        return valid_votes

    except Exception as e:
        print(f"Error parsing votes with Gemini: {e}")
        return {}

def extract_individual_votes_with_gemini():
    # Path to the 2025 meetings data directory
    data_dir = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data"

    # Load the current consolidated data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        consolidated_data = json.load(f)

    print("Extracting individual vote data using Gemini AI...")

    # Find all votable_vote_candidates files
    candidate_files = []
    for file in os.listdir(data_dir):
        if file.startswith('votable_vote_candidates_') and file.endswith('.json'):
            candidate_files.append(os.path.join(data_dir, file))

    print(f"Found {len(candidate_files)} votable_vote_candidates files")

    # Extract individual votes from each file using Gemini
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

                print(f"  Analyzing vote {meeting_id}_{frame_number} with Gemini...")
                individual_votes = parse_votes_with_gemini(raw_text)

                if individual_votes:
                    raw_votes[meeting_id][frame_number] = individual_votes
                    councilmember_names.update(individual_votes.keys())
                    print(f"    Found votes: {individual_votes}")

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
            print(f"Updated vote {vote['id']} with Gemini-parsed individual votes")
        else:
            # Try nearby frame numbers (within 5 frames)
            if meeting_id in raw_votes:
                for raw_frame, individual_votes in raw_votes[meeting_id].items():
                    if abs(raw_frame - frame_number) <= 5:
                        vote['individual_votes'] = individual_votes
                        votes_updated += 1
                        print(f"Updated vote {vote['id']} with Gemini-parsed individual votes (frame {raw_frame}, diff: {abs(raw_frame - frame_number)})")
                        break

    print(f"Updated {votes_updated} votes with Gemini-parsed individual vote data")

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

    print("✅ Individual vote data extracted using Gemini AI and merged successfully!")
    print(f"Updated councilmembers: {consolidated_data['councilmembers']}")

    # Print stats for each councilmember
    for councilmember in sorted(councilmember_names):
        stats = councilmember_stats[councilmember]
        print(f"{councilmember}: {stats['total_votes']} votes ({stats['yes_votes']} yes, {stats['no_votes']} no, {stats['abstentions']} abstain)")

if __name__ == "__main__":
    extract_individual_votes_with_gemini()
