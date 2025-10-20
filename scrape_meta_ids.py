#!/usr/bin/env python3
"""
Scrape meta_ids from Granicus agenda pages to create accurate video deep links
"""

import json
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

def scrape_meta_ids():
    """Scrape meta_ids from Granicus agenda pages"""

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
            # Fetch the agenda page
            response = requests.get(agenda_url, timeout=10)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all links with meta_id parameters
            links = soup.find_all('a', href=True)
            meeting_meta_ids = {}

            for link in links:
                href = link['href']
                if 'meta_id=' in href:
                    # Extract meta_id from URL
                    meta_id_match = re.search(r'meta_id=(\d+)', href)
                    if meta_id_match:
                        meta_id = meta_id_match.group(1)

                        # Get the agenda item text
                        agenda_text = link.get_text(strip=True)
                        if agenda_text:
                            meeting_meta_ids[agenda_text] = meta_id
                            print(f"  Found: {agenda_text[:50]}... -> meta_id={meta_id}")

            meta_id_mapping[meeting_id] = meeting_meta_ids
            print(f"  ✅ Scraped {len(meeting_meta_ids)} agenda items for meeting {meeting_id}")

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
                for agenda_text, meta_id in meeting_meta_ids.items():
                    if agenda_text.lower() in agenda_item.lower() or agenda_item.lower() in agenda_text.lower():
                        vote['meta_id'] = meta_id
                        matched_votes += 1
                        print(f"  ✅ Partial match: {agenda_item[:30]}... -> meta_id={meta_id}")
                        break

    print(f"\n📊 Results:")
    print(f"  Total votes: {total_votes}")
    print(f"  Matched votes: {matched_votes}")
    print(f"  Match rate: {(matched_votes/total_votes)*100:.1f}%")

    # Save updated vote data
    with open('data/torrance_votes_consolidated_final.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"💾 Updated vote data with meta_ids")

if __name__ == '__main__':
    scrape_meta_ids()
