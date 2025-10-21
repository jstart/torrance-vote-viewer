#!/usr/bin/env python3
"""
Remove votes for non-votable agenda items like Oral Communications, Adjournment, etc.
"""

import json

def is_non_votable_agenda_item(agenda_item):
    """Check if an agenda item is non-votable"""
    if not agenda_item:
        return False

    # Handle both string and object agenda items
    if isinstance(agenda_item, str):
        agenda_lower = agenda_item.lower()
    elif isinstance(agenda_item, dict):
        agenda_lower = agenda_item.get('description', '').lower()
    else:
        return False

    # Non-votable agenda item patterns
    non_votable_patterns = [
        'oral communications',
        'adjournment',
        'presentation only',
        'for presentation',
        'announcement',
        'council committee meetings',
        'committee meetings and announcements'
    ]

    return any(pattern in agenda_lower for pattern in non_votable_patterns)

def remove_non_votable_votes():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("Removing votes for non-votable agenda items...")

    # Identify non-votable votes
    non_votable_votes = []
    votable_votes = []

    for vote in data['votes']:
        if is_non_votable_agenda_item(vote.get('agenda_item')):
            non_votable_votes.append(vote)
            print(f"Removing non-votable vote: {vote.get('id', 'unknown')} - {str(vote.get('agenda_item', ''))[:80]}...")
        else:
            votable_votes.append(vote)

    print(f"\nRemoved {len(non_votable_votes)} non-votable votes")
    print(f"Kept {len(votable_votes)} votable votes")

    # Update the data
    data['votes'] = votable_votes

    # Recalculate councilmember stats
    councilmember_stats = {}
    for councilmember in data['councilmembers']:
        councilmember_stats[councilmember] = {
            'total_votes': 0,
            'yes_votes': 0,
            'no_votes': 0,
            'abstentions': 0
        }

    for vote in votable_votes:
        if 'individual_votes' in vote and vote['individual_votes']:
            for cm, vote_result in vote['individual_votes'].items():
                if cm in councilmember_stats:
                    councilmember_stats[cm]['total_votes'] += 1
                    if vote_result == 'YES':
                        councilmember_stats[cm]['yes_votes'] += 1
                    elif vote_result == 'NO':
                        councilmember_stats[cm]['no_votes'] += 1
                    elif vote_result == 'ABSTAIN':
                        councilmember_stats[cm]['abstentions'] += 1

    data['councilmember_stats'] = councilmember_stats

    # Update meeting vote counts
    meeting_vote_counts = {}
    for vote in votable_votes:
        meeting_id = vote.get('meeting_id')
        if meeting_id:
            meeting_vote_counts[meeting_id] = meeting_vote_counts.get(meeting_id, 0) + 1

    # Update meetings data
    for meeting_id, meeting_data in data['meetings'].items():
        if meeting_id in meeting_vote_counts:
            meeting_data['total_votes'] = meeting_vote_counts[meeting_id]
        else:
            meeting_data['total_votes'] = 0

    # Update summaries
    for cm in data['councilmembers']:
        if cm in data['councilmember_summaries']:
            stats = councilmember_stats[cm]
            data['councilmember_summaries'][cm]['notes'] = [
                f"Participated in {stats['total_votes']} recorded votes",
                f"Voted Yes on {stats['yes_votes']} motions",
                f"Voted No on {stats['no_votes']} motions",
                f"Active in {len(set(str(vote.get('agenda_item', '')) for vote in votable_votes if 'individual_votes' in vote and cm in vote['individual_votes']))} policy areas"
            ]
            data['councilmember_summaries'][cm]['stats'] = {
                'total_votes': stats['total_votes'],
                'yes_votes': stats['yes_votes'],
                'no_votes': stats['no_votes']
            }

    # Save the cleaned data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Removed {len(non_votable_votes)} non-votable votes!")
    print(f"📊 Updated vote counts:")
    for cm, stats in councilmember_stats.items():
        print(f"  {cm}: {stats['total_votes']} votes ({stats['yes_votes']} yes, {stats['no_votes']} no, {stats['abstentions']} abstain)")

if __name__ == "__main__":
    remove_non_votable_votes()
