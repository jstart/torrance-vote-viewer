#!/usr/bin/env python3
"""
Fix the MOD23-00010 vote data based on the vote frame image evidence
"""

import json

def fix_mod23_vote():
    """Fix the MOD23-00010 vote based on vote frame evidence"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("🔍 Fixing MOD23-00010 vote data...")
    
    # Find the problematic vote
    target_vote = None
    for vote in data.get('votes', []):
        if (vote.get('agenda_item') and 
            'MOD23-00010' in str(vote.get('agenda_item'))):
            target_vote = vote
            break
    
    if not target_vote:
        print("❌ Vote not found")
        return
    
    print(f"📊 Current (incorrect) data:")
    print(f"   - Result: {target_vote.get('result')}")
    print(f"   - Tally: {target_vote.get('vote_tally')}")
    print(f"   - Individual votes: {target_vote.get('individual_votes')}")
    
    # Fix based on vote frame evidence
    print(f"\n🔧 Fixing based on vote frame evidence...")
    
    # Update result
    target_vote['result'] = 'Motion Passes'
    
    # Update vote tally (all 7 councilmembers voted YES)
    target_vote['vote_tally'] = {
        'ayes': 7,
        'noes': 0,
        'abstentions': 0,
        'recused': 0
    }
    
    # Update individual votes (all councilmembers voted YES)
    target_vote['individual_votes'] = {
        'GEORGE CHEN': 'YES',
        'MIKE GERSON': 'YES',
        'JON KAJI': 'YES',
        'SHARON KALANI': 'YES',
        'ASAM SHEIKH': 'YES',
        'AURELIO MATTUCCI': 'YES',
        'BRIDGET LEWIS': 'YES'
    }
    
    print(f"✅ Fixed vote data:")
    print(f"   - Result: {target_vote.get('result')}")
    print(f"   - Tally: {target_vote.get('vote_tally')}")
    print(f"   - Individual votes: {len(target_vote.get('individual_votes', {}))} councilmembers")
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n💾 Data saved successfully")
    
    # Check for other similar issues
    print(f"\n🔍 Checking for other data accuracy issues...")
    
    # Look for votes with very few councilmembers voting
    suspicious_votes = []
    for vote in data.get('votes', []):
        individual_votes = vote.get('individual_votes', {})
        if len(individual_votes) < 5:  # Less than 5 councilmembers voting
            suspicious_votes.append({
                'meeting_id': vote.get('meeting_id'),
                'agenda_item': str(vote.get('agenda_item', ''))[:50] + '...' if vote.get('agenda_item') else 'No agenda',
                'councilmember_count': len(individual_votes),
                'result': vote.get('result')
            })
    
    print(f"⚠️  Found {len(suspicious_votes)} votes with < 5 councilmembers voting:")
    for vote in suspicious_votes[:10]:  # Show first 10
        print(f"   - Meeting {vote['meeting_id']}: {vote['councilmember_count']} votes - {vote['result']}")
        print(f"     {vote['agenda_item']}")

if __name__ == "__main__":
    fix_mod23_vote()
