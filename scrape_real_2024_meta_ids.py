#!/usr/bin/env python3
"""
Scrape real meta_ids and timestamps from 2024 Torrance meetings
"""

import requests
import re
import time
import json
from bs4 import BeautifulSoup
from datetime import datetime

def scrape_meeting_timestamps(meeting_id):
    """Scrape timestamps for all meta_ids in a meeting"""
    
    url = f"https://torrance.granicus.com/player/clip/{meeting_id}"
    
    try:
        print(f"Scraping timestamps for meeting {meeting_id}...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for timestamp patterns
        timestamp_mappings = {}
        
        # Pattern 1: Look for elements with both data-id and time attributes
        elements = soup.find_all(attrs={"data-id": True, "time": True})
        for element in elements:
            meta_id = element.get('data-id')
            time_attr = element.get('time')
            if meta_id and time_attr and time_attr.isdigit():
                timestamp_mappings[meta_id] = int(time_attr)
        
        # Pattern 2: Look for JavaScript data structures
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Look for patterns like: {id: "123456", time: "1234"}
                js_pattern = r'\{[^}]*id["\']?\s*:\s*["\']?(\d+)["\']?[^}]*time["\']?\s*:\s*["\']?(\d+)["\']?[^}]*\}'
                matches = re.findall(js_pattern, script.string)
                for meta_id, timestamp in matches:
                    timestamp_mappings[meta_id] = int(timestamp)
                
                # Look for patterns like: "376743": {"time": "1234"}
                js_pattern2 = r'"(\d{6,})":\s*\{[^}]*time["\']?\s*:\s*["\']?(\d+)["\']?[^}]*\}'
                matches2 = re.findall(js_pattern2, script.string)
                for meta_id, timestamp in matches2:
                    timestamp_mappings[meta_id] = int(timestamp)
        
        # Pattern 3: Look for chapter/timeline data
        timeline_elements = soup.find_all(attrs={"class": re.compile(r"timeline|chapter|agenda")})
        for element in timeline_elements:
            meta_id = element.get('data-id') or element.get('id')
            time_attr = element.get('time') or element.get('data-time')
            if meta_id and time_attr and meta_id.isdigit() and time_attr.isdigit():
                timestamp_mappings[meta_id] = int(time_attr)
        
        print(f"Found {len(timestamp_mappings)} timestamp mappings")
        return timestamp_mappings
        
    except Exception as e:
        print(f"Error scraping timestamps for meeting {meeting_id}: {e}")
        return {}

def scrape_agenda_items(meeting_id):
    """Scrape agenda items and their associated meta_ids"""
    
    url = f"https://torrance.granicus.com/player/clip/{meeting_id}"
    
    try:
        print(f"Scraping agenda items for meeting {meeting_id}...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        agenda_mappings = {}
        
        # Look for agenda item patterns
        # Pattern 1: Elements with agenda text and meta_id
        agenda_elements = soup.find_all(attrs={"data-id": True})
        for element in agenda_elements:
            meta_id = element.get('data-id')
            agenda_text = element.get_text(strip=True)
            
            # Look for agenda item indicators
            if any(keyword in agenda_text.lower() for keyword in ['consent', 'resolution', 'ordinance', 'hearing', 'adjournment']):
                if meta_id and meta_id.isdigit():
                    agenda_mappings[meta_id] = agenda_text
        
        # Pattern 2: Look in JavaScript for agenda data
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Look for patterns with agenda text and meta_id
                js_pattern = r'\{[^}]*id["\']?\s*:\s*["\']?(\d+)["\']?[^}]*text["\']?\s*:\s*["\']([^"\']+)["\']?[^}]*\}'
                matches = re.findall(js_pattern, script.string)
                for meta_id, agenda_text in matches:
                    if meta_id.isdigit() and len(agenda_text) > 10:
                        agenda_mappings[meta_id] = agenda_text
        
        print(f"Found {len(agenda_mappings)} agenda mappings")
        return agenda_mappings
        
    except Exception as e:
        print(f"Error scraping agenda items for meeting {meeting_id}: {e}")
        return {}

def match_meta_ids_to_votes(meeting_id, timestamp_mappings, agenda_mappings, votes):
    """Match scraped meta_ids to votes based on agenda items"""
    
    meeting_votes = [vote for vote in votes if vote.get('meeting_id') == meeting_id]
    print(f"Matching meta_ids for {len(meeting_votes)} votes in meeting {meeting_id}")
    
    updated_votes = []
    
    for vote in meeting_votes:
        agenda_item = vote.get('agenda_item', '')
        frame_number = vote.get('frame_number', 0)
        
        # Handle case where agenda_item might be a dict
        if isinstance(agenda_item, dict):
            agenda_item = str(agenda_item)
        elif not isinstance(agenda_item, str):
            agenda_item = ''
        
        # Try to find matching meta_id
        best_match = None
        best_score = 0
        
        for meta_id, agenda_text in agenda_mappings.items():
            # Calculate similarity score
            score = 0
            
            # Exact match
            if agenda_item.lower() == agenda_text.lower():
                score = 100
            # Partial match
            elif agenda_item.lower() in agenda_text.lower() or agenda_text.lower() in agenda_item.lower():
                score = 80
            # Keyword match
            elif any(keyword in agenda_text.lower() for keyword in agenda_item.lower().split()):
                score = 60
            
            if score > best_score:
                best_score = score
                best_match = meta_id
        
        # Update vote with real meta_id and timestamp
        if best_match and best_score >= 60:
            vote['meta_id'] = best_match
            vote['video_timestamp'] = timestamp_mappings.get(best_match, frame_number * 30)
            vote['timestamp_estimated'] = False
            print(f"  ✅ Matched: '{agenda_item}' -> meta_id {best_match} (score: {best_score})")
        else:
            # Keep estimated values
            print(f"  ❌ No match: '{agenda_item}' (best score: {best_score})")
        
        updated_votes.append(vote)
    
    return updated_votes

def update_2024_meetings_with_real_meta_ids():
    """Update 2024 meetings with real scraped meta_ids and timestamps"""
    
    # Load current data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    # Get 2024 meeting IDs
    meeting_ids = []
    for meeting_id, meeting in data['meetings'].items():
        if meeting.get('date', '').startswith('2024'):
            meeting_ids.append(meeting_id)
    
    print(f"Processing {len(meeting_ids)} 2024 meetings: {meeting_ids}")
    
    # Process each meeting
    total_updated = 0
    
    for meeting_id in meeting_ids:
        print(f"\n=== Processing Meeting {meeting_id} ===")
        
        # Scrape timestamps and agenda items
        timestamp_mappings = scrape_meeting_timestamps(meeting_id)
        agenda_mappings = scrape_agenda_items(meeting_id)
        
        if timestamp_mappings and agenda_mappings:
            # Match to votes
            updated_votes = match_meta_ids_to_votes(
                meeting_id, 
                timestamp_mappings, 
                agenda_mappings, 
                data['votes']
            )
            
            # Update the votes in data
            for i, vote in enumerate(data['votes']):
                if vote.get('meeting_id') == meeting_id:
                    data['votes'][i] = updated_votes.pop(0)
                    total_updated += 1
        
        time.sleep(2)  # Be respectful to the server
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✅ Updated {total_updated} votes with real meta_ids and timestamps!")
    print(f"📊 Results:")
    print(f"   - Meetings processed: {len(meeting_ids)}")
    print(f"   - Votes updated: {total_updated}")

if __name__ == "__main__":
    update_2024_meetings_with_real_meta_ids()
