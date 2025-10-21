#!/usr/bin/env python3
"""
Generate meeting summaries for all meetings without summaries
"""

import json
from collections import defaultdict

def generate_meeting_summary(meeting_id, meeting_data, votes):
    """Generate a comprehensive meeting summary based on vote data"""

    # Get meeting details
    title = meeting_data.get('title', f'City Council Meeting {meeting_id}')
    date = meeting_data.get('date', 'Unknown date')
    total_votes = len(votes)
    passed_votes = sum(1 for vote in votes if 'pass' in vote.get('result', '').lower())
    failed_votes = sum(1 for vote in votes if 'fail' in vote.get('result', '').lower())

    # Analyze vote topics
    topics = defaultdict(int)
    for vote in votes:
        agenda_item = vote.get('agenda_item', '')
        if isinstance(agenda_item, str):
            agenda_text = agenda_item.lower()
        elif isinstance(agenda_item, dict):
            agenda_text = agenda_item.get('description', '').lower()
        else:
            agenda_text = ''

        # Categorize by topic
        if 'consent calendar' in agenda_text:
            topics['Consent Calendar'] += 1
        elif 'administrative matters' in agenda_text:
            topics['Administrative Matters'] += 1
        elif 'planning' in agenda_text or 'development' in agenda_text:
            topics['Planning & Development'] += 1
        elif 'fire' in agenda_text or 'police' in agenda_text or 'public safety' in agenda_text:
            topics['Public Safety'] += 1
        elif 'finance' in agenda_text or 'budget' in agenda_text or 'appropriation' in agenda_text:
            topics['Budget & Finance'] += 1
        elif 'transit' in agenda_text or 'transportation' in agenda_text:
            topics['Transportation'] += 1
        elif 'community services' in agenda_text or 'parks' in agenda_text:
            topics['Community Services'] += 1
        elif 'environmental' in agenda_text or 'sustainability' in agenda_text:
            topics['Environmental'] += 1
        elif 'housing' in agenda_text or 'affordable housing' in agenda_text:
            topics['Housing'] += 1
        elif 'honoring' in agenda_text or 'proclamation' in agenda_text or 'resolution' in agenda_text:
            topics['Recognition & Proclamations'] += 1
        elif 'hearing' in agenda_text:
            topics['Public Hearings'] += 1
        elif 'adjournment' in agenda_text:
            topics['Adjournment'] += 1
        elif 'oral communications' in agenda_text:
            topics['Public Comment'] += 1
        else:
            topics['Other Business'] += 1

    # Get top topics
    top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]

    # Analyze councilmember participation
    councilmember_votes = defaultdict(int)
    for vote in votes:
        if vote.get('individual_votes') and isinstance(vote['individual_votes'], dict):
            for councilmember in vote['individual_votes'].keys():
                councilmember_votes[councilmember] += 1

    # Generate summary
    summary_parts = []

    # Opening
    summary_parts.append(f"The Torrance City Council convened on {date} for a regular meeting.")

    # Vote overview
    if total_votes > 0:
        summary_parts.append(f"The council conducted {total_votes} votes, with {passed_votes} motions passing and {failed_votes} motions failing.")

    # Key topics
    if top_topics:
        topic_list = [f"{topic} ({count} items)" for topic, count in top_topics]
        summary_parts.append(f"Key agenda topics included: {', '.join(topic_list)}.")

    # Notable votes
    notable_votes = []
    for vote in votes:
        agenda_item = vote.get('agenda_item', '')
        if isinstance(agenda_item, dict):
            agenda_text = agenda_item.get('description', '')
        else:
            agenda_text = agenda_item

        result = vote.get('result', '')

        # Look for significant votes
        if agenda_text and any(keyword in agenda_text.lower() for keyword in ['budget', 'appropriation', 'ordinance', 'resolution', 'contract', 'agreement']):
            if 'pass' in result.lower():
                notable_votes.append(f"Approved {agenda_text[:60]}...")
            elif 'fail' in result.lower():
                notable_votes.append(f"Rejected {agenda_text[:60]}...")

    if notable_votes:
        summary_parts.append(f"Notable actions included: {'; '.join(notable_votes[:3])}.")

    # Councilmember participation
    if councilmember_votes:
        active_members = sorted(councilmember_votes.items(), key=lambda x: x[1], reverse=True)
        summary_parts.append(f"All councilmembers participated actively, with {active_members[0][0]} voting on {active_members[0][1]} items.")

    # Closing
    summary_parts.append("The meeting concluded with standard adjournment procedures.")

    return ' '.join(summary_parts)

def generate_all_meeting_summaries():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    meetings = data.get('meetings', {})
    votes = data.get('votes', [])

    # Group votes by meeting
    votes_by_meeting = defaultdict(list)
    for vote in votes:
        meeting_id = vote.get('meeting_id')
        if meeting_id:
            votes_by_meeting[meeting_id].append(vote)

    # Generate summaries for meetings without them
    summaries_generated = 0

    for meeting_id, meeting_data in meetings.items():
        if not meeting_data.get('summary'):
            meeting_votes = votes_by_meeting.get(meeting_id, [])
            summary = generate_meeting_summary(meeting_id, meeting_data, meeting_votes)

            meeting_data['summary'] = summary
            summaries_generated += 1

            print(f"Generated summary for meeting {meeting_id} ({meeting_data.get('title', 'Unknown')})")
            print(f"  Votes: {len(meeting_votes)}")
            print(f"  Summary: {summary[:100]}...")
            print()

    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Generated {summaries_generated} meeting summaries!")
    print(f"📊 Total meetings: {len(meetings)}")
    print(f"📝 Meetings with summaries: {summaries_generated}")

if __name__ == "__main__":
    generate_all_meeting_summaries()
