#!/usr/bin/env python3
"""
Script to generate detailed councilmember summaries using actual vote history.
"""

import json
import os

def generate_detailed_summaries():
    """Generate detailed councilmember summaries based on actual voting data."""
    
    # Load the data with individual votes
    with open('data/torrance_votes_with_individual_votes.json', 'r') as f:
        data = json.load(f)
    
    print("🔍 Generating detailed councilmember summaries...")
    
    # Get all councilmembers
    councilmembers = data.get('councilmembers', [])
    print(f"Found {len(councilmembers)} councilmembers: {councilmembers}")
    
    detailed_summaries = {}
    
    for councilmember_name in councilmembers:
        print(f"\n📋 Processing {councilmember_name}...")
        
        # Get all votes for this councilmember
        councilmember_votes = []
        for vote in data.get('votes', []):
            if vote.get('individual_votes'):
                for individual_vote in vote['individual_votes']:
                    if individual_vote.get('name') == councilmember_name:
                        councilmember_votes.append({
                            'meeting_id': vote.get('meeting_id'),
                            'meeting_date': vote.get('meeting_date'),
                            'agenda_item': vote.get('agenda_item'),
                            'vote_result': individual_vote.get('result'),
                            'overall_result': vote.get('result'),
                            'motion_text': vote.get('motion_text')
                        })
        
        print(f"  Found {len(councilmember_votes)} votes")
        
        if not councilmember_votes:
            # Create a basic summary for councilmembers with no individual vote data
            detailed_summaries[councilmember_name] = {
                'summary': f"{councilmember_name} is a member of the Torrance City Council. Limited individual voting data is available in the current dataset, as most votes show only overall tally results rather than individual positions.",
                'role': 'Councilmember' if councilmember_name != 'Chen' else 'Mayor',
                'notes': [
                    'Individual vote positions not available in current dataset',
                    'Most votes show only overall results (pass/fail)',
                    'Limited voting history data for detailed analysis'
                ]
            }
            continue
        
        # Analyze voting patterns
        yes_votes = sum(1 for vote in councilmember_votes if vote['vote_result'] == 'Y')
        no_votes = sum(1 for vote in councilmember_votes if vote['vote_result'] == 'N')
        abstentions = sum(1 for vote in councilmember_votes if vote['vote_result'] == 'A')
        
        # Get unique agenda items voted on
        agenda_items = list(set(vote['agenda_item'] for vote in councilmember_votes if vote['agenda_item']))
        
        # Determine role
        role = 'Mayor' if councilmember_name == 'Chen' else 'Councilmember'
        
        # Generate summary based on voting patterns
        if yes_votes > 0 and no_votes == 0:
            voting_pattern = "consistently supportive"
        elif yes_votes > no_votes:
            voting_pattern = "generally supportive"
        elif no_votes > yes_votes:
            voting_pattern = "generally cautious"
        else:
            voting_pattern = "balanced"
        
        # Create detailed summary
        summary = f"{councilmember_name} serves as {role.lower()} of the Torrance City Council. "
        
        if len(councilmember_votes) > 0:
            summary += f"Based on available voting records, {councilmember_name} has participated in {len(councilmember_votes)} recorded votes, showing a {voting_pattern} approach to council decisions. "
            
            if yes_votes > 0:
                summary += f"Voted 'Yes' on {yes_votes} motions, "
            if no_votes > 0:
                summary += f"'No' on {no_votes} motions, "
            if abstentions > 0:
                summary += f"and abstained on {abstentions} motions. "
            
            summary += f"Key areas of focus include {', '.join(agenda_items[:3]) if agenda_items else 'various council matters'}."
        else:
            summary += "Limited individual voting data is available in the current dataset."
        
        # Generate notes
        notes = []
        if len(councilmember_votes) > 0:
            notes.append(f"Participated in {len(councilmember_votes)} recorded votes")
            if yes_votes > 0:
                notes.append(f"Voted 'Yes' on {yes_votes} motions")
            if no_votes > 0:
                notes.append(f"Voted 'No' on {no_votes} motions")
            if abstentions > 0:
                notes.append(f"Abstained on {abstentions} motions")
            
            # Add agenda item categories
            if agenda_items:
                notes.append(f"Voted on {len(agenda_items)} different agenda items")
        else:
            notes.append("No individual vote data available")
        
        detailed_summaries[councilmember_name] = {
            'summary': summary,
            'role': role,
            'notes': notes,
            'voting_stats': {
                'total_votes': len(councilmember_votes),
                'yes_votes': yes_votes,
                'no_votes': no_votes,
                'abstentions': abstentions,
                'agenda_items_count': len(agenda_items)
            }
        }
    
    # Update the data file
    data['councilmember_summaries'] = detailed_summaries
    
    # Save updated data
    with open('data/torrance_votes_with_individual_votes.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✅ Generated detailed summaries for {len(detailed_summaries)} councilmembers")
    print("📊 Summary of generated summaries:")
    for name, summary_data in detailed_summaries.items():
        print(f"  {name}: {summary_data['voting_stats']['total_votes']} votes, {summary_data['role']}")
    
    return detailed_summaries

if __name__ == "__main__":
    generate_detailed_summaries()
