#!/usr/bin/env python3
"""
Comprehensive Gemini-based vote processor to ensure all vote records are accurate
Processes ALL votable frames through Gemini to correct vote data discrepancies
"""

import json
import os
import re
import google.generativeai as genai
from tqdm import tqdm
import time

# Configure Gemini API
genai.configure(api_key="AIzaSyBvOkBwJcTTTMc8yD13D8awxWg5U_OPYrU")
model = genai.GenerativeModel('gemini-1.5-flash')

def extract_votes_with_gemini(raw_text, meeting_id, vote_id):
    """Extract individual votes using Gemini with enhanced prompting"""
    
    # Enhanced prompt for better accuracy
    prompt = f"""
    You are analyzing a city council meeting vote record. Extract the individual votes for each councilmember.
    
    IMPORTANT: Look carefully at the raw text and identify ALL councilmembers and their votes.
    Common councilmembers in Torrance City Council:
    - George Chen (Mayor)
    - Mike Gerson
    - Jon Kaji  
    - Sharon Kalani
    - Asam Sheikh
    - Bridget Lewis
    - Aurelio Mattucci
    
    Vote options are: YES, NO, ABSTAIN, RECUSE
    
    Raw Text from Meeting {meeting_id}, Vote {vote_id}:
    {raw_text}
    
    Return ONLY a JSON object with this exact format:
    {{
      "GEORGE CHEN": "YES",
      "MIKE GERSON": "NO", 
      "JON KAJI": "YES",
      "SHARON KALANI": "NO",
      "ASAM SHEIKH": "NO",
      "BRIDGET LEWIS": "NO",
      "AURELIO MATTUCCI": "YES"
    }}
    
    If a councilmember's vote is unclear or missing, use "ABSTAIN".
    If a councilmember is not present, do not include them in the JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        json_string = response.text.strip()
        
        # Clean up common markdown formatting
        json_string = json_string.replace('```json', '').replace('```', '').strip()
        
        # Parse JSON
        votes = json.loads(json_string)
        
        # Validate and normalize vote values
        normalized_votes = {}
        for councilmember, vote in votes.items():
            vote_upper = str(vote).upper().strip()
            if vote_upper in ['YES', 'Y', 'YEA', 'AYE']:
                normalized_votes[councilmember] = 'YES'
            elif vote_upper in ['NO', 'N', 'NAY']:
                normalized_votes[councilmember] = 'NO'
            elif vote_upper in ['ABSTAIN', 'ABSTENTION', 'A']:
                normalized_votes[councilmember] = 'ABSTAIN'
            elif vote_upper in ['RECUSE', 'R']:
                normalized_votes[councilmember] = 'RECUSE'
            else:
                normalized_votes[councilmember] = 'ABSTAIN'  # Default for unclear votes
        
        return normalized_votes
        
    except Exception as e:
        print(f"Error processing vote {vote_id} in meeting {meeting_id}: {e}")
        return None

def process_all_votable_frames():
    """Process all votable frame files through Gemini"""
    
    data_dir = '/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data'
    consolidated_file = 'data/torrance_votes_smart_consolidated.json'
    
    # Load consolidated data
    with open(consolidated_file, 'r') as f:
        consolidated_data = json.load(f)
    
    print(f"📊 Starting comprehensive Gemini processing...")
    print(f"📁 Processing files from: {data_dir}")
    
    # Find all votable_vote_candidates files
    votable_files = []
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file.startswith('votable_vote_candidates_') and file.endswith('.json'):
                votable_files.append(os.path.join(root, file))
    
    print(f"📋 Found {len(votable_files)} votable frame files to process")
    
    # Process each file
    all_gemini_votes = {}
    processed_files = 0
    total_votes_processed = 0
    
    for file_path in tqdm(votable_files, desc="Processing votable frames"):
        try:
            with open(file_path, 'r') as f:
                votable_data = json.load(f)
            
            file_votes = 0
            for i, vote_entry in enumerate(votable_data):
                meeting_id = vote_entry.get('meeting_id')
                raw_text = vote_entry.get('raw_text')
                frame_number = vote_entry.get('frame_number', i)
                
                if meeting_id and raw_text:
                    # Create a unique vote ID from frame number
                    vote_id = f"frame_{frame_number}"
                    
                    # Process with Gemini
                    gemini_votes = extract_votes_with_gemini(raw_text, meeting_id, vote_id)
                    
                    if gemini_votes:
                        if meeting_id not in all_gemini_votes:
                            all_gemini_votes[meeting_id] = {}
                        all_gemini_votes[meeting_id][vote_id] = gemini_votes
                        file_votes += 1
                        total_votes_processed += 1
                        
                        # Show progress for important votes
                        if 'AURELIO MATTUCCI' in gemini_votes:
                            print(f"  ✅ Found Mattucci vote: {gemini_votes['AURELIO MATTUCCI']} in meeting {meeting_id}, frame {frame_number}")
            
            processed_files += 1
            print(f"📄 Processed {file_path}: {file_votes} votes")
            
            # Rate limiting - pause between files
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ Error processing file {file_path}: {e}")
            continue
    
    print(f"\n📊 Processing Summary:")
    print(f"  Files processed: {processed_files}")
    print(f"  Total votes processed: {total_votes_processed}")
    print(f"  Meetings with votes: {len(all_gemini_votes)}")
    
    # Update consolidated data with Gemini results
    votes_updated = 0
    councilmembers_found = set()
    
    # Create a mapping from meeting_id + frame_number to Gemini votes
    frame_vote_mapping = {}
    for meeting_id, votes in all_gemini_votes.items():
        for vote_id, gemini_votes in votes.items():
            if vote_id.startswith('frame_'):
                frame_number = int(vote_id.replace('frame_', ''))
                frame_vote_mapping[(meeting_id, frame_number)] = gemini_votes
    
    for vote in consolidated_data['votes']:
        meeting_id = vote.get('meeting_id')
        frame_number = vote.get('frame_number')
        
        if meeting_id and frame_number and (meeting_id, frame_number) in frame_vote_mapping:
            old_votes = vote.get('individual_votes', {})
            new_votes = frame_vote_mapping[(meeting_id, frame_number)]
            
            # Update individual votes
            vote['individual_votes'] = new_votes
            votes_updated += 1
            
            # Track councilmembers found
            for cm in new_votes.keys():
                councilmembers_found.add(cm)
            
            # Show changes for Mattucci specifically
            if 'AURELIO MATTUCCI' in new_votes:
                old_mattucci = old_votes.get('AURELIO MATTUCCI', 'NOT FOUND')
                new_mattucci = new_votes['AURELIO MATTUCCI']
                if old_mattucci != new_mattucci:
                    print(f"🔄 Mattucci vote changed: {old_mattucci} → {new_mattucci} (meeting {meeting_id}, frame {frame_number})")
    
    # Update councilmembers list
    consolidated_data['councilmembers'] = sorted(list(councilmembers_found))
    
    # Recalculate vote tallies and councilmember stats
    print(f"\n🔄 Recalculating vote tallies and councilmember stats...")
    
    # Initialize councilmember stats
    councilmember_stats = {cm: {"total_votes": 0, "yes_votes": 0, "no_votes": 0, "abstentions": 0, "recused": 0} for cm in consolidated_data['councilmembers']}
    
    # Recalculate all vote tallies and stats
    for vote in consolidated_data['votes']:
        if 'individual_votes' in vote and isinstance(vote['individual_votes'], dict):
            individual_votes = vote['individual_votes']
            
            # Count votes for tally
            ayes = sum(1 for v in individual_votes.values() if v == 'YES')
            noes = sum(1 for v in individual_votes.values() if v == 'NO')
            abstentions = sum(1 for v in individual_votes.values() if v == 'ABSTAIN')
            recused = sum(1 for v in individual_votes.values() if v == 'RECUSE')
            
            # Update vote tally
            vote['vote_tally'] = {
                'ayes': ayes,
                'noes': noes,
                'abstentions': abstentions,
                'recused': recused
            }
            
            # Update result based on tally
            if ayes > noes:
                vote['result'] = 'Motion Passes'
            elif noes > ayes:
                vote['result'] = 'Motion Fails'
            else:
                vote['result'] = 'Tie'
            
            # Update councilmember stats
            for councilmember, vote_result in individual_votes.items():
                if councilmember in councilmember_stats:
                    councilmember_stats[councilmember]["total_votes"] += 1
                    if vote_result == 'YES':
                        councilmember_stats[councilmember]["yes_votes"] += 1
                    elif vote_result == 'NO':
                        councilmember_stats[councilmember]["no_votes"] += 1
                    elif vote_result == 'ABSTAIN':
                        councilmember_stats[councilmember]["abstentions"] += 1
                    elif vote_result == 'RECUSE':
                        councilmember_stats[councilmember]["recused"] += 1
    
    consolidated_data['councilmember_stats'] = councilmember_stats
    
    # Save updated data
    with open(consolidated_file, 'w') as f:
        json.dump(consolidated_data, f, indent=2)
    
    print(f"\n✅ Comprehensive Gemini processing completed!")
    print(f"📊 Votes updated: {votes_updated}")
    print(f"👥 Councilmembers found: {sorted(list(councilmembers_found))}")
    
    # Show Mattucci stats specifically
    if 'AURELIO MATTUCCI' in councilmember_stats:
        matt_stats = councilmember_stats['AURELIO MATTUCCI']
        print(f"\n🎯 Aurelio Mattucci stats:")
        print(f"  Total votes: {matt_stats['total_votes']}")
        print(f"  Yes votes: {matt_stats['yes_votes']}")
        print(f"  No votes: {matt_stats['no_votes']}")
        print(f"  Abstentions: {matt_stats['abstentions']}")
        print(f"  Recused: {matt_stats['recused']}")
    
    return consolidated_data

if __name__ == "__main__":
    process_all_votable_frames()
