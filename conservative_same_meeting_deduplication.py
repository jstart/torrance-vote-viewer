#!/usr/bin/env python3
"""
Conservative Same-Meeting Deduplication
Only removes obvious duplicates (very short descriptions or identical content) within same meetings.
"""

import json
from collections import defaultdict

def conservative_same_meeting_deduplication():
    """Remove only obvious duplicates with same frame numbers within same meetings"""

    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("=== CONSERVATIVE SAME-MEETING DEDUPLICATION ===")

    # Group votes by meeting and frame number
    meeting_frame_groups = defaultdict(list)
    for vote in data.get('votes', []):
        meeting_id = vote.get('meeting_id')
        frame_num = vote.get('frame_number')

        if meeting_id and frame_num is not None and frame_num != 'N/A':
            try:
                frame_num = int(frame_num)
                meeting_frame_groups[(meeting_id, frame_num)].append(vote)
            except (ValueError, TypeError):
                continue

    # Process each group
    votes_to_remove = set()
    duplicates_removed = 0

    for (meeting_id, frame_num), votes in meeting_frame_groups.items():
        if len(votes) > 1:
            print(f"\n🔍 Meeting {meeting_id}, Frame {frame_num}: {len(votes)} votes - checking for obvious duplicates")

            # Only remove votes that are clearly duplicates (very short descriptions)
            obvious_duplicates = []
            legitimate_votes = []

            for vote in votes:
                agenda_item = vote.get('agenda_item')
                if isinstance(agenda_item, dict):
                    text = agenda_item.get('description', '')
                elif isinstance(agenda_item, str):
                    text = agenda_item
                else:
                    text = str(agenda_item) if agenda_item else ''

                # Check if this is an obvious duplicate (very short or placeholder text)
                is_obvious_duplicate = (
                    len(text) <= 5 or  # Very short
                    text in ['10', '9A', '9B', '9C', '9D', '9E', '9F', '9G', '9H', '9I', '9J', '9K', '9L', '9M', '9N', '9O', '9P', '9Q', '9R', '9S', '9T', '9U', '9V', '9W', '9X', '9Y', '9Z'] or
                    text in ['10A', '10B', '10C', '10D', '10E', '10F', '10G', '10H', '10I', '10J', '10K', '10L', '10M', '10N', '10O', '10P', '10Q', '10R', '10S', '10T', '10U', '10V', '10W', '10X', '10Y', '10Z'] or
                    text in ['1A', '1B', '1C', '1D', '1E', '1F', '1G', '1H', '1I', '1J', '1K', '1L', '1M', '1N', '1O', '1P', '1Q', '1R', '1S', '1T', '1U', '1V', '1W', '1X', '1Y', '1Z'] or
                    text in ['2A', '2B', '2C', '2D', '2E', '2F', '2G', '2H', '2I', '2J', '2K', '2L', '2M', '2N', '2O', '2P', '2Q', '2R', '2S', '2T', '2U', '2V', '2W', '2X', '2Y', '2Z'] or
                    text in ['3A', '3B', '3C', '3D', '3E', '3F', '3G', '3H', '3I', '3J', '3K', '3L', '3M', '3N', '3O', '3P', '3Q', '3R', '3S', '3T', '3U', '3V', '3W', '3X', '3Y', '3Z'] or
                    text in ['4A', '4B', '4C', '4D', '4E', '4F', '4G', '4H', '4I', '4J', '4K', '4L', '4M', '4N', '4O', '4P', '4Q', '4R', '4S', '4T', '4U', '4V', '4W', '4X', '4Y', '4Z'] or
                    text in ['5A', '5B', '5C', '5D', '5E', '5F', '5G', '5H', '5I', '5J', '5K', '5L', '5M', '5N', '5O', '5P', '5Q', '5R', '5S', '5T', '5U', '5V', '5W', '5X', '5Y', '5Z'] or
                    text in ['6A', '6B', '6C', '6D', '6E', '6F', '6G', '6H', '6I', '6J', '6K', '6L', '6M', '6N', '6O', '6P', '6Q', '6R', '6S', '6T', '6U', '6V', '6W', '6X', '6Y', '6Z'] or
                    text in ['7A', '7B', '7C', '7D', '7E', '7F', '7G', '7H', '7I', '7J', '7K', '7L', '7M', '7N', '7O', '7P', '7Q', '7R', '7S', '7T', '7U', '7V', '7W', '7X', '7Y', '7Z'] or
                    text in ['8A', '8B', '8C', '8D', '8E', '8F', '8G', '8H', '8I', '8J', '8K', '8L', '8M', '8N', '8O', '8P', '8Q', '8R', '8S', '8T', '8U', '8V', '8W', '8X', '8Y', '8Z'] or
                    text in ['11A', '11B', '11C', '11D', '11E', '11F', '11G', '11H', '11I', '11J', '11K', '11L', '11M', '11N', '11O', '11P', '11Q', '11R', '11S', '11T', '11U', '11V', '11W', '11X', '11Y', '11Z'] or
                    text in ['12A', '12B', '12C', '12D', '12E', '12F', '12G', '12H', '12I', '12J', '12K', '12L', '12M', '12N', '12O', '12P', '12Q', '12R', '12S', '12T', '12U', '12V', '12W', '12X', '12Y', '12Z'] or
                    text in ['13A', '13B', '13C', '13D', '13E', '13F', '13G', '13H', '13I', '13J', '13K', '13L', '13M', '13N', '13O', '13P', '13Q', '13R', '13S', '13T', '13U', '13V', '13W', '13X', '13Y', '13Z'] or
                    text in ['14A', '14B', '14C', '14D', '14E', '14F', '14G', '14H', '14I', '14J', '14K', '14L', '14M', '14N', '14O', '14P', '14Q', '14R', '14S', '14T', '14U', '14V', '14W', '14X', '14Y', '14Z'] or
                    text in ['15A', '15B', '15C', '15D', '15E', '15F', '15G', '15H', '15I', '15J', '15K', '15L', '15M', '15N', '15O', '15P', '15Q', '15R', '15S', '15T', '15U', '15V', '15W', '15X', '15Y', '15Z'] or
                    text in ['16A', '16B', '16C', '16D', '16E', '16F', '16G', '16H', '16I', '16J', '16K', '16L', '16M', '16N', '16O', '16P', '16Q', '16R', '16S', '16T', '16U', '16V', '16W', '16X', '16Y', '16Z'] or
                    text in ['17A', '17B', '17C', '17D', '17E', '17F', '17G', '17H', '17I', '17J', '17K', '17L', '17M', '17N', '17O', '17P', '17Q', '17R', '17S', '17T', '17U', '17V', '17W', '17X', '17Y', '17Z'] or
                    text in ['18A', '18B', '18C', '18D', '18E', '18F', '18G', '18H', '18I', '18J', '18K', '18L', '18M', '18N', '18O', '18P', '18Q', '18R', '18S', '18T', '18U', '18V', '18W', '18X', '18Y', '18Z'] or
                    text in ['19A', '19B', '19C', '19D', '19E', '19F', '19G', '19H', '19I', '19J', '19K', '19L', '19M', '19N', '19O', '19P', '19Q', '19R', '19S', '19T', '19U', '19V', '19W', '19X', '19Y', '19Z'] or
                    text in ['20A', '20B', '20C', '20D', '20E', '20F', '20G', '20H', '20I', '20J', '20K', '20L', '20M', '20N', '20O', '20P', '20Q', '20R', '20S', '20T', '20U', '20V', '20W', '20X', '20Y', '20Z'] or
                    text in ['None', 'Not visible in image', 'Not visible in the image', 'Unknown Agenda Item'] or
                    text == '' or
                    text.endswith('...')  # Truncated descriptions
                )

                if is_obvious_duplicate:
                    obvious_duplicates.append(vote)
                else:
                    legitimate_votes.append(vote)

            # Only remove obvious duplicates if there are legitimate votes to keep
            if obvious_duplicates and legitimate_votes:
                print(f"    Found {len(obvious_duplicates)} obvious duplicates, {len(legitimate_votes)} legitimate votes")

                for vote in obvious_duplicates:
                    votes_to_remove.add(vote.get('id'))
                    duplicates_removed += 1
                    agenda_display = str(vote.get('agenda_item', 'N/A'))[:30]
                    print(f"    ❌ Removing obvious duplicate: {vote.get('id')} - {agenda_display}...")

                for vote in legitimate_votes:
                    agenda_display = str(vote.get('agenda_item', 'N/A'))[:30]
                    print(f"    ✅ Keeping legitimate: {vote.get('id')} - {agenda_display}...")
            else:
                print(f"    No obvious duplicates found - keeping all {len(votes)} votes")

    # Remove duplicate votes
    original_count = len(data['votes'])
    data['votes'] = [vote for vote in data['votes'] if vote.get('id') not in votes_to_remove]
    removed_count = original_count - len(data['votes'])

    print(f"\n✅ Removed {removed_count} obvious duplicate votes")
    print(f"✅ Final vote count: {len(data['votes'])}")

    # Update meeting metadata
    print(f"\n📊 Updating meeting metadata...")
    meetings_updated = 0

    for meeting_id, meeting_data in data.get('meetings', {}).items():
        meeting_votes = [vote for vote in data['votes'] if vote.get('meeting_id') == meeting_id]

        new_total_votes = len(meeting_votes)
        new_passed_votes = sum(1 for vote in meeting_votes if 'pass' in vote.get('result', '').lower())
        new_failed_votes = sum(1 for vote in meeting_votes if 'fail' in vote.get('result', '').lower())

        if (meeting_data.get('total_votes') != new_total_votes or
            meeting_data.get('passed_votes') != new_passed_votes or
            meeting_data.get('failed_votes') != new_failed_votes):

            print(f"  Meeting {meeting_id}: {meeting_data.get('total_votes', 'N/A')} → {new_total_votes} votes")
            meeting_data['total_votes'] = new_total_votes
            meeting_data['passed_votes'] = new_passed_votes
            meeting_data['failed_votes'] = new_failed_votes
            meetings_updated += 1

    print(f"  ✅ Updated {meetings_updated} meetings")

    # Save the updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ CONSERVATIVE SAME-MEETING DEDUPLICATION COMPLETE!")
    print(f"📊 Summary:")
    print(f"  - Obvious duplicates removed: {removed_count}")
    print(f"  - Meetings updated: {meetings_updated}")
    print(f"  - Final vote count: {len(data['votes'])}")

if __name__ == "__main__":
    conservative_same_meeting_deduplication()
