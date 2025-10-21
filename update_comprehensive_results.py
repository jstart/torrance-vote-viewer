#!/usr/bin/env python3
"""
Update comprehensive results to reflect current data state
"""

import json
from datetime import datetime

def update_comprehensive_results():
    # Load current consolidated data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        consolidated_data = json.load(f)

    # Count meetings and votes by year
    meetings_by_year = {}
    votes_by_meeting = {}

    for vote in consolidated_data['votes']:
        meeting_id = vote.get('meeting_id', '')
        if meeting_id:
            votes_by_meeting[meeting_id] = votes_by_meeting.get(meeting_id, 0) + 1

            # Determine year based on meeting ID
            if meeting_id.startswith('145'):
                year = '2025'
            elif meeting_id.startswith('144'):
                year = '2024'
            elif meeting_id.startswith('143'):
                year = '2024'
            elif meeting_id.startswith('142'):
                year = '2024'
            else:
                year = 'unknown'

            if year not in meetings_by_year:
                meetings_by_year[year] = set()
            meetings_by_year[year].add(meeting_id)

    # Create updated comprehensive results
    updated_results = {
        "processing_summary": {
            "total_meetings": len(consolidated_data.get('meetings', {})),
            "completed_meetings": len(consolidated_data.get('meetings', {})),
            "total_frames_processed": 0,  # We don't track this in consolidated data
            "total_vote_candidates": 0,   # We don't track this in consolidated data
            "total_votes_extracted": len(consolidated_data.get('votes', [])),
            "start_time": 1760905027.414906,  # Keep original start time
            "last_updated": datetime.now().isoformat(),
            "current_meeting": "completed"
        },
        "meeting_results": []
    }

    # Add meeting results for each meeting in the consolidated data
    for meeting_id, meeting_data in consolidated_data.get('meetings', {}).items():
        vote_count = votes_by_meeting.get(meeting_id, 0)

        # Determine year
        if meeting_id.startswith('145'):
            year = '2025'
        elif meeting_id.startswith('144') or meeting_id.startswith('143') or meeting_id.startswith('142'):
            year = '2024'
        else:
            year = 'unknown'

        meeting_result = {
            "meeting_id": meeting_id,
            "status": "completed",
            "year": year,
            "frame_count": 0,  # We don't track this in consolidated data
            "vote_candidates": 0,  # We don't track this in consolidated data
            "votes_extracted": vote_count,
            "processing_time": 0,  # We don't track this in consolidated data
            "meeting_date": meeting_data.get('date', 'unknown'),
            "meeting_title": meeting_data.get('title', 'unknown')
        }

        updated_results["meeting_results"].append(meeting_result)

    # Sort meetings by ID (which will group by year)
    updated_results["meeting_results"].sort(key=lambda x: x["meeting_id"])

    # Add summary by year
    updated_results["year_summary"] = {}
    for year, meetings in meetings_by_year.items():
        total_votes = sum(votes_by_meeting.get(meeting_id, 0) for meeting_id in meetings)
        updated_results["year_summary"][year] = {
            "meetings": len(meetings),
            "votes": total_votes,
            "meeting_ids": sorted(list(meetings))
        }

    # Save updated results
    with open('data/comprehensive_2025_results.json', 'w') as f:
        json.dump(updated_results, f, indent=2)

    print("✅ Updated comprehensive results!")
    print(f"📊 Total meetings: {updated_results['processing_summary']['total_meetings']}")
    print(f"📊 Total votes: {updated_results['processing_summary']['total_votes_extracted']}")
    print(f"📊 Year breakdown:")
    for year, summary in updated_results["year_summary"].items():
        print(f"  {year}: {summary['meetings']} meetings, {summary['votes']} votes")

if __name__ == "__main__":
    update_comprehensive_results()
