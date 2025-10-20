#!/usr/bin/env python3
"""
Extract meta_ids from Granicus agenda pages using curl
"""

import json
import subprocess
import re

def extract_meta_ids_with_curl():
    """Extract meta_ids from Granicus agenda pages using curl"""
    
    # Load our vote data
    with open('data/torrance_votes_consolidated_final.json', 'r') as f:
        data = json.load(f)
    
    # Get all unique meeting IDs
    meeting_ids = list(data['meetings'].keys())
    print(f"Found {len(meeting_ids)} meetings to scrape: {meeting_ids}")
    
    meta_id_mapping = {}
    
    for meeting_id in meeting_ids:
        print(f"\n🔍 Scraping meeting {meeting_id}...")
        
        # Construct agenda URL
        agenda_url = f"https://torrance.granicus.com/GeneratedAgendaViewer.php?view_id=8&clip_id={meeting_id}"
        
        try:
            # Use curl to fetch the page
            result = subprocess.run(['curl', '-s', agenda_url], 
                                 capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                html_content = result.stdout
                
                # Extract all meta_ids from the HTML
                meta_ids = re.findall(r'meta_id=(\d+)', html_content)
                
                # Extract agenda item text and meta_id pairs
                agenda_items = re.findall(r'href="[^"]*meta_id=(\d+)[^"]*"[^>]*>([^<]+)</a>', html_content)
                
                meeting_meta_ids = {}
                for meta_id, agenda_text in agenda_items:
                    agenda_text = agenda_text.strip()
                    if agenda_text and len(agenda_text) > 5:  # Filter out very short text
                        meeting_meta_ids[agenda_text] = meta_id
                        print(f"  Found: {agenda_text[:50]}... -> meta_id={meta_id}")
                
                meta_id_mapping[meeting_id] = meeting_meta_ids
                print(f"  ✅ Scraped {len(meeting_meta_ids)} agenda items for meeting {meeting_id}")
                
            else:
                print(f"  ❌ Error fetching meeting {meeting_id}")
                meta_id_mapping[meeting_id] = {}
                
        except Exception as e:
            print(f"  ❌ Error scraping meeting {meeting_id}: {e}")
            meta_id_mapping[meeting_id] = {}
    
    # Save the mapping
    with open('data/meta_id_mapping.json', 'w') as f:
        json.dump(meta_id_mapping, f, indent=2)
    
    print(f"\n💾 Saved meta_id mapping to data/meta_id_mapping.json")
    
    # Now try to match our votes to the scraped meta_ids
    print(f"\n🔗 Matching votes to meta_ids...")
    
    matched_votes = 0
    total_votes = len(data['votes'])
    
    for vote in data['votes']:
        meeting_id = vote['meeting_id']
        agenda_item = vote.get('agenda_item', '')
        
        if meeting_id in meta_id_mapping and agenda_item:
            # Try to find matching meta_id
            meeting_meta_ids = meta_id_mapping[meeting_id]
            
            # Look for exact match first
            if agenda_item in meeting_meta_ids:
                vote['meta_id'] = meeting_meta_ids[agenda_item]
                matched_votes += 1
                print(f"  ✅ Exact match: {agenda_item[:30]}... -> meta_id={vote['meta_id']}")
            else:
                # Try partial matches
                best_match = None
                best_score = 0
                
                for agenda_text, meta_id in meeting_meta_ids.items():
                    # Calculate similarity score
                    agenda_lower = agenda_item.lower()
                    text_lower = agenda_text.lower()
                    
                    # Check if one contains the other
                    if agenda_lower in text_lower or text_lower in agenda_lower:
                        score = len(set(agenda_lower.split()) & set(text_lower.split()))
                        if score > best_score:
                            best_score = score
                            best_match = meta_id
                
                if best_match:
                    vote['meta_id'] = best_match
                    matched_votes += 1
                    print(f"  ✅ Partial match: {agenda_item[:30]}... -> meta_id={best_match}")
    
    print(f"\n📊 Results:")
    print(f"  Total votes: {total_votes}")
    print(f"  Matched votes: {matched_votes}")
    print(f"  Match rate: {(matched_votes/total_votes)*100:.1f}%")
    
    # Save updated vote data
    with open('data/torrance_votes_consolidated_final.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"💾 Updated vote data with meta_ids")

if __name__ == '__main__':
    extract_meta_ids_with_curl()
