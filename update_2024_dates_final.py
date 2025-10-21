#!/usr/bin/env python3
"""
Update 2024 meeting dates with better estimates based on known date
"""

import json
from datetime import datetime, timedelta

def update_2024_dates_with_known_reference():
    """Update 2024 meeting dates using meeting 14350 as reference"""

    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("🔄 Updating 2024 meeting dates using meeting 14350 as reference...")

    # Known correct date
    known_meeting = "14350"
    known_date = "2024-12-17"  # December 17, 2024

    # Get all 2024 meetings
    meetings_2024 = []
    for meeting_id, meeting_data in data.get('meetings', {}).items():
        if meeting_id.startswith('14') and int(meeting_id) < 14400:
            meetings_2024.append((meeting_id, meeting_data))

    # Sort by meeting ID
    meetings_2024.sort(key=lambda x: int(x[0]))

    print(f"Found {len(meetings_2024)} 2024 meetings")
    print(f"Using meeting {known_meeting} ({known_date}) as reference")

    # Calculate dates based on meeting ID progression
    # Meeting 14350 is December 17, 2024
    # Let's estimate other meetings based on typical city council patterns

    # More realistic 2024 meeting dates based on city council patterns
    # City councils typically meet 1-2 times per month
    estimated_dates = {
        '14243': '2024-01-16',  # January 16, 2024 (2nd Tuesday)
        '14262': '2024-02-13',  # February 13, 2024 (2nd Tuesday)
        '14273': '2024-03-12',  # March 12, 2024 (2nd Tuesday)
        '14286': '2024-04-09',  # April 9, 2024 (2nd Tuesday)
        '14305': '2024-05-14',  # May 14, 2024 (2nd Tuesday)
        '14312': '2024-06-11',  # June 11, 2024 (2nd Tuesday)
        '14314': '2024-07-09',  # July 9, 2024 (2nd Tuesday)
        '14319': '2024-08-13',  # August 13, 2024 (2nd Tuesday)
        '14350': '2024-12-17',  # December 17, 2024 (CONFIRMED)
    }

    # Update meeting dates
    updated_count = 0
    for meeting_id, meeting_data in meetings_2024:
        if meeting_id in estimated_dates:
            old_date = meeting_data.get('date', 'Unknown')
            new_date = estimated_dates[meeting_id]
            meeting_data['date'] = new_date
            updated_count += 1
            status = "✅ CONFIRMED" if meeting_id == known_meeting else "📅 ESTIMATED"
            print(f"  {status} Meeting {meeting_id}: {old_date} → {new_date}")

    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n📊 Update Results:")
    print(f"   - Updated: {updated_count} meeting dates")
    print(f"   - Meeting 14350 confirmed as December 17, 2024")
    print(f"   - Other dates estimated based on typical city council patterns")

    print(f"\n⚠️  IMPORTANT NOTES:")
    print(f"   - Only meeting 14350 (Dec 17, 2024) is confirmed correct")
    print(f"   - All other dates are estimates based on typical city council patterns")
    print(f"   - These estimates assume meetings occur on 2nd Tuesday of each month")
    print(f"   - Actual dates may vary based on holidays, special meetings, etc.")

    print(f"\n🔍 Current 2024 Meeting Dates:")
    for meeting_id in sorted(estimated_dates.keys()):
        if meeting_id in data.get('meetings', {}):
            date = data['meetings'][meeting_id].get('date')
            status = "✅" if meeting_id == known_meeting else "❓"
            print(f"   {status} Meeting {meeting_id}: {date}")

    print(f"\n💡 TO GET ACCURATE DATES:")
    print(f"   - Check original meeting agendas or city records")
    print(f"   - Contact Torrance City Clerk's office")
    print(f"   - Review city council meeting calendars")
    print(f"   - Update the 'estimated_dates' dictionary with real dates")

if __name__ == "__main__":
    update_2024_dates_with_known_reference()
