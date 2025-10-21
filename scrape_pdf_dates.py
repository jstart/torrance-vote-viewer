#!/usr/bin/env python3
"""
Extract meeting dates from PDF agenda documents
"""

import requests
import json
import re
from datetime import datetime
import io

def extract_pdf_text(pdf_url):
    """Extract text from PDF URL"""
    try:
        response = requests.get(pdf_url, timeout=10)
        response.raise_for_status()

        # Simple PDF text extraction (basic approach)
        # This is a simplified version - in practice you'd use PyPDF2 or similar
        content = response.content

        # Look for text patterns in the PDF content
        # PDFs often have text in readable format even if compressed
        text_content = content.decode('utf-8', errors='ignore')

        return text_content
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return ""

def scrape_meeting_dates_from_pdfs():
    """Scrape actual meeting dates from PDF agenda documents"""

    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("🔍 Scraping actual meeting dates from PDF agenda documents...")

    # Get all 2024 meetings
    meetings_2024 = []
    for meeting_id, meeting_data in data.get('meetings', {}).items():
        if meeting_id.startswith('14') and int(meeting_id) < 14400:
            meetings_2024.append((meeting_id, meeting_data))

    print(f"Found {len(meetings_2024)} 2024 meetings to check")

    # Scrape dates from PDF documents
    scraped_dates = {}

    for meeting_id, meeting_data in meetings_2024:
        print(f"\n📋 Checking Meeting {meeting_id}...")

        # Use the correct agenda URL format
        agenda_url = f"https://torrance.granicus.com/AgendaViewer.php?view_id=8&clip_id={meeting_id}"

        try:
            # Make request to get the PDF URL
            session = requests.Session()
            response = session.get(agenda_url, timeout=10, allow_redirects=True)
            response.raise_for_status()

            final_url = response.url
            print(f"  PDF URL: {final_url}")

            # Extract text from PDF
            pdf_text = extract_pdf_text(final_url)

            if pdf_text:
                print(f"  PDF text length: {len(pdf_text)} characters")

                # Look for date patterns in the PDF text
                date_patterns = [
                    r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{1,2},?\s+\d{4}',  # MONTH DD, YYYY
                    r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY
                    r'(\d{4}-\d{2}-\d{2})',      # YYYY-MM-DD
                ]

                date_found = False
                for pattern in date_patterns:
                    matches = re.findall(pattern, pdf_text, re.IGNORECASE)
                    if matches:
                        # Take the first date found
                        date_str = matches[0]
                        print(f"  Found date in PDF: {date_str}")
                        scraped_dates[meeting_id] = date_str
                        date_found = True
                        break

                if not date_found:
                    print(f"  ❌ No date found in PDF for meeting {meeting_id}")
                    # Print first 500 characters to see what we got
                    print(f"  PDF preview: {pdf_text[:500]}...")
            else:
                print(f"  ❌ Could not extract text from PDF for meeting {meeting_id}")

        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error accessing {agenda_url}: {e}")
        except Exception as e:
            print(f"  ❌ Error processing meeting {meeting_id}: {e}")

    # Display results
    print(f"\n📊 Scraping Results:")
    print(f"   - Successfully scraped: {len(scraped_dates)} dates")

    if scraped_dates:
        print(f"\n🔍 Scraped Dates:")
        for meeting_id, date_str in scraped_dates.items():
            print(f"   - Meeting {meeting_id}: {date_str}")

    # Save scraped dates to file for review
    with open('scraped_pdf_2024_dates.json', 'w') as f:
        json.dump(scraped_dates, f, indent=2)

    print(f"\n💾 Scraped dates saved to 'scraped_pdf_2024_dates.json'")
    print(f"   - Review the dates and update the main data file if they look correct")

if __name__ == "__main__":
    scrape_meeting_dates_from_pdfs()
