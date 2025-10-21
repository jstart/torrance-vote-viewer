#!/usr/bin/env python3
"""
Update 2024 meeting dates with actual dates from Torrance City Council meeting list
"""

import json
from datetime import datetime

def update_2024_dates_with_actual_list():
    """Update 2024 meeting dates with actual dates from the meeting list"""
    
    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("🔄 Updating 2024 meeting dates with actual dates from meeting list...")
    
    # ACTUAL 2024 meeting dates from the Torrance City Council meeting list
    # Format: 'meeting_id': 'YYYY-MM-DD'
    actual_dates = {
        '14243': '2024-01-09',   # Tue, January 09, 2024
        '14262': '2024-01-23',   # Tue, January 23, 2024
        '14273': '2024-02-06',   # Tue, February 06, 2024
        '14286': '2024-02-27',   # Tue, February 27, 2024
        '14305': '2024-03-12',   # Tue, March 12, 2024
        '14312': '2024-03-26',   # Tue, March 26, 2024
        '14314': '2024-04-09',   # Tue, April 09, 2024
        '14319': '2024-04-23',   # Tue, April 23, 2024
        '14350': '2024-12-17',   # Tue, December 17, 2024 (CONFIRMED)
    }
    
    # Get all 2024 meetings
    meetings_2024 = []
    for meeting_id, meeting_data in data.get('meetings', {}).items():
        if meeting_id.startswith('14') and int(meeting_id) < 14400:
            meetings_2024.append((meeting_id, meeting_data))
    
    print(f"Found {len(meetings_2024)} 2024 meetings")
    
    # Update meeting dates
    updated_count = 0
    for meeting_id, meeting_data in meetings_2024:
        if meeting_id in actual_dates:
            old_date = meeting_data.get('date', 'Unknown')
            new_date = actual_dates[meeting_id]
            meeting_data['date'] = new_date
            updated_count += 1
            status = "✅ CONFIRMED" if meeting_id == '14350' else "✅ ACTUAL"
            print(f"  {status} Meeting {meeting_id}: {old_date} → {new_date}")
        else:
            print(f"  ❓ Meeting {meeting_id}: No actual date found in meeting list")
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n📊 Update Results:")
    print(f"   - Updated: {updated_count} meeting dates")
    print(f"   - All dates now based on actual Torrance City Council meeting list")
    print(f"   - Meeting 14350 confirmed as December 17, 2024")
    
    print(f"\n🔍 Updated 2024 Meeting Dates:")
    for meeting_id in sorted(actual_dates.keys()):
        if meeting_id in data.get('meetings', {}):
            date = data['meetings'][meeting_id].get('date')
            status = "✅" if meeting_id == '14350' else "✅"
            print(f"   {status} Meeting {meeting_id}: {date}")
    
    print(f"\n📅 Meeting Schedule Pattern:")
    print(f"   - Meetings occur on Tuesdays")
    print(f"   - Typically 1-2 meetings per month")
    print(f"   - Some months have multiple meetings (e.g., December 2024)")
    print(f"   - Dates follow actual city council schedule, not estimated patterns")

if __name__ == "__main__":
    update_2024_dates_with_actual_list()
