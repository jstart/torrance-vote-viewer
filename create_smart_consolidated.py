#!/usr/bin/env python3
"""
Script to create a consolidated dataset that preserves more votes
by being smarter about deduplication.
"""

import json
import os
from collections import defaultdict

def create_smart_consolidated_data():
    """Create a consolidated dataset with smarter deduplication."""
    
    # Load original data
    source_file = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data/consolidated_votes_with_agenda.json"
    with open(source_file, 'r') as f:
        original_data = json.load(f)
    
    print(f"📊 Original data: {len(original_data['all_votes'])} votes")
    
    # Load individual vote data
    individual_votes_by_meeting = defaultdict(list)
    
    # Process all votable_votes files for individual vote data
    source_dir = "/Users/christophertruman/Downloads/torrance-council-votes-new/2025_meetings_data"
    for file_name in os.listdir(source_dir):
        if file_name.startswith('votable_votes_') and file_name.endswith('.json'):
            file_path = os.path.join(source_dir, file_name)
            
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                if isinstance(data, list):
                    for vote in data:
                        if 'council_member_votes' in vote and vote['council_member_votes']:
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
                                
            except Exception as e:
                print(f"⚠️ Error reading {file_name}: {e}")
    
    print(f"📊 Individual vote data: {sum(len(votes) for votes in individual_votes_by_meeting.values())} votes")
    
    # Create mapping from meeting_id + agenda_item to individual votes
    individual_votes_map = {}
    for meeting_id, votes in individual_votes_by_meeting.items():
        for vote in votes:
            key = f"{meeting_id}_{vote.get('agenda_item', 'unknown')}"
            individual_votes_map[key] = vote['individual_votes']
    
    # Smart deduplication: Keep votes that are different results or have different frame numbers
    processed_votes = []
    seen_votes = set()
    
    for vote in original_data['all_votes']:
        meeting_id = vote.get('meeting_id')
        agenda_item = vote.get('agenda_item')
        result = vote.get('result')
        frame_number = vote.get('frame_number')
        
        # Create a more specific key that includes result and frame number
        vote_key = f"{meeting_id}_{agenda_item}_{result}_{frame_number}"
        
        # Only skip if we've seen this exact vote before
        if vote_key in seen_votes:
            continue
        
        seen_votes.add(vote_key)
        
        # Try to find matching individual votes
        agenda_key = f"{meeting_id}_{agenda_item}"
        if agenda_key in individual_votes_map:
            vote['individual_votes'] = individual_votes_map[agenda_key]
        else:
            vote['individual_votes'] = None
        
        processed_votes.append(vote)
    
    print(f"📊 Processed votes: {len(processed_votes)} votes")
    
    # Calculate meeting statistics
    meetings = {}
    for vote in processed_votes:
        meeting_id = vote.get('meeting_id')
        if meeting_id not in meetings:
            meetings[meeting_id] = {
                'id': meeting_id,
                'title': f'City Council Meeting',
                'date': '2025-08-05',  # Default date, should be updated
                'total_votes': 0,
                'video_url': f'https://torrance.granicus.com/player/clip/{meeting_id}',
                'agenda_url': f'https://torrance.granicus.com/GeneratedAgendaViewer.php?view_id=8&clip_id={meeting_id}'
            }
        meetings[meeting_id]['total_votes'] += 1
    
    # Calculate councilmember statistics
    councilmember_stats = {}
    all_councilmember_names = set()
    
    for vote in processed_votes:
        if vote.get('individual_votes'):
            for individual_vote in vote['individual_votes']:
                name = individual_vote.get('name')
                if name:
                    all_councilmember_names.add(name)
                    
                    if name not in councilmember_stats:
                        councilmember_stats[name] = {
                            'total_votes': 0,
                            'yes_votes': 0,
                            'no_votes': 0
                        }
                    
                    councilmember_stats[name]['total_votes'] += 1
                    result = individual_vote.get('result', '').upper()
                    if result == 'Y':
                        councilmember_stats[name]['yes_votes'] += 1
                    elif result == 'N':
                        councilmember_stats[name]['no_votes'] += 1
    
    # Create the consolidated data structure
    consolidated_data = {
        'metadata': {
            'created_at': '2025-10-20T16:30:00Z',
            'total_votes': len(processed_votes),
            'total_meetings': len(meetings),
            'total_councilmembers': len(all_councilmember_names),
            'votes_with_individual_data': len([v for v in processed_votes if v.get('individual_votes')])
        },
        'votes': processed_votes,
        'meetings': meetings,
        'councilmembers': sorted(list(all_councilmember_names)),
        'councilmember_stats': councilmember_stats,
        'agenda_items': sorted(list(set(v.get('agenda_item') for v in processed_votes if v.get('agenda_item')))),
        'years': ['2025'],
        'routes': {
            'home': '/',
            'meetings': '/meetings',
            'councilmembers': '/councilmembers',
            'search': '/search',
            'year': '/year/2025'
        }
    }
    
    # Add meeting summaries (placeholder)
    consolidated_data['meeting_summaries'] = {}
    for meeting_id in meetings:
        consolidated_data['meeting_summaries'][meeting_id] = {
            'summary': f'City Council meeting with {meetings[meeting_id]["total_votes"]} votes recorded.',
            'unique_aspects': ['Standard procedural meeting'],
            'key_items': []
        }
    
    # Add councilmember summaries (placeholder)
    consolidated_data['councilmember_summaries'] = {}
    for name in all_councilmember_names:
        stats = councilmember_stats.get(name, {'total_votes': 0, 'yes_votes': 0, 'no_votes': 0})
        role = 'Mayor' if name == 'Chen' else 'Councilmember'
        
        consolidated_data['councilmember_summaries'][name] = {
            'summary': f'{name} serves as {role.lower()} of the Torrance City Council. Based on available voting records, {name} has participated in {stats["total_votes"]} recorded votes.',
            'role': role,
            'notes': [f'Participated in {stats["total_votes"]} recorded votes']
        }
    
    # Save the consolidated data
    output_file = 'data/torrance_votes_smart_consolidated.json'
    with open(output_file, 'w') as f:
        json.dump(consolidated_data, f, indent=2)
    
    print(f"\n✅ Created smart consolidated data: {output_file}")
    print(f"📊 Final stats:")
    print(f"  Total votes: {len(processed_votes)}")
    print(f"  Total meetings: {len(meetings)}")
    print(f"  Councilmembers: {len(all_councilmember_names)}")
    print(f"  Votes with individual data: {len([v for v in processed_votes if v.get('individual_votes')])}")
    
    return output_file

if __name__ == "__main__":
    create_smart_consolidated_data()
