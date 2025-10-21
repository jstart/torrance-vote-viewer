#!/usr/bin/env python3
"""
Scrape actual meeting dates from Granicus agenda pages
"""

import requests
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup

def scrape_agenda_dates():
    """Scrape actual meeting dates from Granicus agenda pages"""

    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("🔍 Scraping actual meeting dates from Granicus agenda pages...")

    # Get all 2024 meetings
    meetings_2024 = []
    for meeting_id, meeting_data in data.get('meetings', {}).items():
        if meeting_id.startswith('14') and int(meeting_id) < 14400:
            meetings_2024.append((meeting_id, meeting_data))

    print(f"Found {len(meetings_2024)} 2024 meetings to check")

    # Scrape dates from agenda pages
    scraped_dates = {}

    for meeting_id, meeting_data in meetings_2024:
        print(f"\n📋 Checking Meeting {meeting_id}...")

        # Get agenda URL
        agenda_url = meeting_data.get('agenda_url')
        if not agenda_url:
            print(f"  ❌ No agenda URL for meeting {meeting_id}")
            continue

        print(f"  Agenda URL: {agenda_url}")

        try:
            # Make request to agenda page
            response = requests.get(agenda_url, timeout=10)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for date information in various places
            date_found = False

            # Method 1: Look for date in title
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text()
                print(f"  Title: {title_text}")

                # Try to extract date from title
                date_patterns = [
                    r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY
                    r'(\d{4}-\d{2}-\d{2})',      # YYYY-MM-DD
                    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',  # Month DD, YYYY
                ]

                for pattern in date_patterns:
                    match = re.search(pattern, title_text)
                    if match:
                        date_str = match.group(1)
                        print(f"  Found date in title: {date_str}")
                        scraped_dates[meeting_id] = date_str
                        date_found = True
                        break

            # Method 2: Look for date in page content
            if not date_found:
                page_text = soup.get_text()

                # Look for common date patterns
                date_patterns = [
                    r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY
                    r'(\d{4}-\d{2}-\d{2})',      # YYYY-MM-DD
                    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',  # Month DD, YYYY
                ]

                for pattern in date_patterns:
                    matches = re.findall(pattern, page_text)
                    if matches:
                        # Take the first date found
                        date_str = matches[0]
                        print(f"  Found date in content: {date_str}")
                        scraped_dates[meeting_id] = date_str
                        date_found = True
                        break

            # Method 3: Look for specific meeting date elements
            if not date_found:
                # Look for elements that might contain meeting dates
                date_elements = soup.find_all(['h1', 'h2', 'h3', 'div', 'span'], string=re.compile(r'\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}'))
                for element in date_elements:
                    text = element.get_text().strip()
                    print(f"  Potential date element: {text}")
                    if re.search(r'\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}', text):
                        scraped_dates[meeting_id] = text
                        date_found = True
                        break

            if not date_found:
                print(f"  ❌ No date found for meeting {meeting_id}")

        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error accessing {agenda_url}: {e}")
        except Exception as e:
            print(f"  ❌ Error parsing page for meeting {meeting_id}: {e}")

    # Display results
    print(f"\n📊 Scraping Results:")
    print(f"   - Successfully scraped: {len(scraped_dates)} dates")

    if scraped_dates:
        print(f"\n🔍 Scraped Dates:")
        for meeting_id, date_str in scraped_dates.items():
            print(f"   - Meeting {meeting_id}: {date_str}")

    # Save scraped dates to file for review
    with open('scraped_2024_agenda_dates.json', 'w') as f:
        json.dump(scraped_dates, f, indent=2)

    print(f"\n💾 Scraped dates saved to 'scraped_2024_agenda_dates.json'")
    print(f"   - Review the dates and update the main data file if they look correct")

if __name__ == "__main__":
    scrape_agenda_dates()
