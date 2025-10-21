#!/usr/bin/env python3
"""
Investigate and scrape real meta_ids from 2024 Torrance meetings
"""

import requests
import re
import time
import json
from bs4 import BeautifulSoup

def test_meeting_access(meeting_id):
    """Test different URL patterns to access 2024 meetings"""
    
    urls_to_try = [
        f"https://torrance.granicus.com/player/clip/{meeting_id}",
        f"https://torrance.granicus.com/ViewPublisher.php?view_id=2&clip_id={meeting_id}",
        f"https://torrance.granicus.com/player/clip/{meeting_id}?view_id=2",
        f"https://torrance.granicus.com/player/clip/{meeting_id}?view_id=8",
        f"https://torrance.granicus.com/player/clip/{meeting_id}?view_id=1",
        f"https://torrance.granicus.com/player/clip/{meeting_id}?view_id=3",
    ]
    
    print(f"\n=== Testing Meeting {meeting_id} ===")
    
    for url in urls_to_try:
        try:
            print(f"Trying: {url}")
            response = requests.get(url, timeout=10)
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"  ✅ SUCCESS! Meeting {meeting_id} is accessible")
                
                # Look for meta_id patterns in the HTML
                meta_ids = re.findall(r'data-id="(\d+)"', response.text)
                meta_ids.extend(re.findall(r'meta_id="(\d+)"', response.text))
                meta_ids.extend(re.findall(r'"id":\s*(\d+)', response.text))
                meta_ids.extend(re.findall(r'clip_id.*?(\d{6,})', response.text))
                
                if meta_ids:
                    print(f"  Found meta_ids: {meta_ids[:10]}")
                    return url, meta_ids[:10]
                else:
                    print(f"  No meta_ids found in HTML")
                    
                    # Check if it's a redirect or different content
                    if "granicus" in response.text.lower():
                        print(f"  Contains Granicus content - might be accessible")
                        return url, []
            else:
                print(f"  ❌ Failed: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    return None, []

def scrape_meeting_meta_ids(meeting_id, url):
    """Scrape meta_ids from a specific meeting URL"""
    
    try:
        print(f"\nScraping meta_ids from meeting {meeting_id}...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for various meta_id patterns
        meta_ids = []
        
        # Pattern 1: data-id attributes
        data_ids = soup.find_all(attrs={"data-id": True})
        for element in data_ids:
            meta_ids.append(element.get('data-id'))
        
        # Pattern 2: meta_id attributes
        meta_id_elements = soup.find_all(attrs={"meta_id": True})
        for element in meta_id_elements:
            meta_ids.append(element.get('meta_id'))
        
        # Pattern 3: JavaScript variables
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Look for meta_id patterns in JavaScript
                js_meta_ids = re.findall(r'meta_id["\']?\s*:\s*["\']?(\d+)', script.string)
                meta_ids.extend(js_meta_ids)
                
                js_meta_ids = re.findall(r'"id":\s*(\d+)', script.string)
                meta_ids.extend(js_meta_ids)
        
        # Pattern 4: Look for chapter/chapter data
        chapters = soup.find_all(attrs={"class": re.compile(r"chapter|agenda|item")})
        for chapter in chapters:
            chapter_id = chapter.get('id') or chapter.get('data-id')
            if chapter_id and chapter_id.isdigit():
                meta_ids.append(chapter_id)
        
        # Remove duplicates and filter
        unique_meta_ids = list(set([mid for mid in meta_ids if mid and mid.isdigit() and len(mid) >= 4]))
        
        print(f"Found {len(unique_meta_ids)} unique meta_ids: {unique_meta_ids[:10]}")
        
        return unique_meta_ids
        
    except Exception as e:
        print(f"Error scraping meeting {meeting_id}: {e}")
        return []

def investigate_2024_meetings():
    """Investigate access to 2024 meetings and scrape meta_ids"""
    
    # Load the 2024 meeting IDs
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    # Get 2024 meeting IDs
    meeting_ids = []
    for meeting_id, meeting in data['meetings'].items():
        if meeting.get('date', '').startswith('2024'):
            meeting_ids.append(meeting_id)
    
    print(f"Found {len(meeting_ids)} 2024 meetings: {meeting_ids}")
    
    # Test access to each meeting
    accessible_meetings = {}
    
    for meeting_id in meeting_ids[:5]:  # Test first 5 meetings
        url, meta_ids = test_meeting_access(meeting_id)
        if url:
            accessible_meetings[meeting_id] = {
                'url': url,
                'meta_ids': meta_ids
            }
        
        time.sleep(2)  # Be respectful to the server
    
    print(f"\n=== SUMMARY ===")
    print(f"Accessible meetings: {len(accessible_meetings)}")
    
    for meeting_id, info in accessible_meetings.items():
        print(f"Meeting {meeting_id}: {info['url']}")
        if info['meta_ids']:
            print(f"  Meta IDs: {info['meta_ids']}")
        else:
            print(f"  No meta IDs found")
    
    return accessible_meetings

if __name__ == "__main__":
    investigate_2024_meetings()
