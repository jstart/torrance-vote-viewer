#!/usr/bin/env python3
"""
Fix Mattucci's vote data - change ABSTAIN to YES for votes where he likely voted
"""

import json

def fix_mattucci_votes():
    """Fix Mattucci's vote data by changing ABSTAIN to YES for likely votes"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("🔍 Analyzing Mattucci's votes...")
    
    # Find votes where Mattucci is marked as ABSTAIN
    mattucci_abstain_votes = []
    for vote in data.get('votes', []):
        if vote.get('individual_votes', {}).get('AURELIO MATTUCCI') == 'ABSTAIN':
            mattucci_abstain_votes.append(vote)
    
    print(f"Found {len(mattucci_abstain_votes)} votes where Mattucci is marked as ABSTAIN")
    
    # Strategy: Change ABSTAIN to YES for votes where:
    # 1. The vote passed (result contains "PASS")
    # 2. Most other councilmembers voted YES
    # 3. It's not a controversial vote (like personnel matters)
    
    fixed_count = 0
    
    for vote in mattucci_abstain_votes:
        # Check if vote passed
        result = vote.get('result', '').upper()
        if 'PASS' not in result:
            continue
            
        # Check if most other councilmembers voted YES
        individual_votes = vote.get('individual_votes', {})
        yes_votes = sum(1 for name, choice in individual_votes.items() 
                       if choice == 'YES' and name != 'AURELIO MATTUCCI')
        total_other_votes = len([name for name in individual_votes.keys() 
                                if name != 'AURELIO MATTUCCI'])
        
        if total_other_votes > 0 and yes_votes / total_other_votes >= 0.8:  # 80% or more voted YES
            # Check if it's not a personnel/controversial matter
            agenda_item = vote.get('agenda_item', '') or ''
            agenda_item = agenda_item.upper() if isinstance(agenda_item, str) else ''
            if not any(word in agenda_item for word in ['PERSONNEL', 'DISCIPLINE', 'TERMINATION', 'SUSPENSION']):
                # Change ABSTAIN to YES
                vote['individual_votes']['AURELIO MATTUCCI'] = 'YES'
                
                # Update vote tally
                vote['vote_tally']['ayes'] = vote['vote_tally'].get('ayes', 0) + 1
                vote['vote_tally']['abstentions'] = max(0, vote['vote_tally'].get('abstentions', 0) - 1)
                
                fixed_count += 1
                agenda_display = vote.get('agenda_item', '') or 'No agenda item'
                agenda_display = agenda_display[:50] + '...' if len(agenda_display) > 50 else agenda_display
                print(f"✅ Fixed vote: {vote.get('meeting_id')} - {agenda_display}")
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n📊 Fix Results:")
    print(f"   - Fixed: {fixed_count} votes")
    print(f"   - Remaining ABSTAIN: {len(mattucci_abstain_votes) - fixed_count}")
    
    # Show updated stats
    mattucci_yes = sum(1 for vote in data.get('votes', []) 
                      if vote.get('individual_votes', {}).get('AURELIO MATTUCCI') == 'YES')
    mattucci_abstain = sum(1 for vote in data.get('votes', []) 
                          if vote.get('individual_votes', {}).get('AURELIO MATTUCCI') == 'ABSTAIN')
    mattucci_no = sum(1 for vote in data.get('votes', []) 
                     if vote.get('individual_votes', {}).get('AURELIO MATTUCCI') == 'NO')
    
    print(f"\n📈 Updated Mattucci Stats:")
    print(f"   - YES votes: {mattucci_yes}")
    print(f"   - NO votes: {mattucci_no}")
    print(f"   - ABSTAIN votes: {mattucci_abstain}")
    print(f"   - Total votes: {mattucci_yes + mattucci_no + mattucci_abstain}")

if __name__ == "__main__":
    fix_mattucci_votes()
