#!/usr/bin/env python3
"""
Script to merge meta_ids from the mapping file into our vote data.
This will enable proper video deep linking with timestamps.
"""

import json
import os

def merge_meta_ids():
    """Merge meta_ids from mapping into vote data."""
    
    # Load the meta_id mapping
    with open('data/meta_id_mapping.json', 'r') as f:
        meta_mapping = json.load(f)
    
    # Load the current vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    votes = data.get('votes', [])
    print(f"🔍 Processing {len(votes)} votes...")
    
    matches_found = 0
    total_votes = len(votes)
    
    for i, vote in enumerate(votes):
        meeting_id = str(vote.get('meeting_id', ''))
        vote_agenda = vote.get('agenda_item', '')
        
        if not meeting_id or not vote_agenda:
            continue
            
        # Get meta_ids for this meeting
        meeting_meta = meta_mapping.get(meeting_id, {})
        if not meeting_meta:
            continue
        
        # Try to find matching meta_id
        meta_id = None
        for meta_key, meta_id_value in meeting_meta.items():
            # Strategy 1: Exact match
            if vote_agenda == meta_key:
                meta_id = meta_id_value
                break
            
            # Strategy 2: Vote agenda contains meta key (most common case)
            if meta_key.lower() in vote_agenda.lower():
                meta_id = meta_id_value
                break
            
            # Strategy 3: Meta key contains vote agenda
            if vote_agenda.lower() in meta_key.lower():
                meta_id = meta_id_value
                break
        
        if meta_id:
            vote['meta_id'] = meta_id
            matches_found += 1
            print(f"✅ Vote {i+1}: \"{vote_agenda[:50]}...\" -> meta_id: {meta_id}")
        else:
            print(f"❌ Vote {i+1}: \"{vote_agenda[:50]}...\" -> No meta_id match")
    
    print(f"\n📊 Summary:")
    print(f"  Total votes: {total_votes}")
    print(f"  Matches found: {matches_found}")
    print(f"  Success rate: {matches_found/total_votes*100:.1f}%")
    
    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n💾 Updated data saved to data/torrance_votes_smart_consolidated.json")
    
    # Verify the update
    votes_with_meta_id = [v for v in votes if v.get('meta_id')]
    print(f"✅ Verification: {len(votes_with_meta_id)} votes now have meta_id")

if __name__ == "__main__":
    merge_meta_ids()
