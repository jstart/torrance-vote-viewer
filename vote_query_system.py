#!/usr/bin/env python3
"""
Torrance Vote Viewer - Query System
Provides functions to query votes by various criteria for web viewer
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Union
from dataclasses import dataclass

@dataclass
class VoteQuery:
    """Query parameters for filtering votes"""
    councilmember: Optional[str] = None
    meeting_id: Optional[str] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    agenda_item: Optional[str] = None
    result: Optional[str] = None  # 'passed', 'failed', or None for all
    limit: Optional[int] = None
    offset: Optional[int] = 0

class TorranceVoteQuerySystem:
    """Main query system for Torrance city council votes"""

    def __init__(self, data_file: str = "data/torrance_votes_consolidated.json"):
        """Initialize the query system with data file"""
        self.data_file = data_file
        self.data = self._load_data()

    def _load_data(self) -> Dict:
        """Load vote data from JSON file"""
        if not os.path.exists(self.data_file):
            raise FileNotFoundError(f"Data file not found: {self.data_file}")

        with open(self.data_file, 'r') as f:
            return json.load(f)

    def get_all_votes(self, query: VoteQuery = None) -> List[Dict]:
        """Get all votes, optionally filtered by query parameters"""
        votes = self.data['votes']

        if query is None:
            return votes

        # Apply filters
        filtered_votes = votes

        # Filter by councilmember
        if query.councilmember:
            filtered_votes = [
                v for v in filtered_votes
                if v['individual_votes'] and any(
                    query.councilmember.lower() in vote_detail.get('name', '').lower()
                    for vote_detail in v['individual_votes']
                )
            ]

        # Filter by meeting ID
        if query.meeting_id:
            filtered_votes = [v for v in filtered_votes if v['meeting_id'] == query.meeting_id]

        # Filter by agenda item
        if query.agenda_item:
            filtered_votes = [
                v for v in filtered_votes
                if v['agenda_item'] and query.agenda_item.lower() in v['agenda_item'].lower()
            ]

        # Filter by result
        if query.result:
            if query.result.lower() == 'passed':
                filtered_votes = [v for v in filtered_votes if 'pass' in v['result'].lower()]
            elif query.result.lower() == 'failed':
                filtered_votes = [v for v in filtered_votes if 'fail' in v['result'].lower()]

        # Apply pagination
        if query.offset:
            filtered_votes = filtered_votes[query.offset:]
        if query.limit:
            filtered_votes = filtered_votes[:query.limit]

        return filtered_votes

    def get_votes_by_councilmember(self, councilmember: str) -> List[Dict]:
        """Get all votes for a specific councilmember"""
        query = VoteQuery(councilmember=councilmember)
        return self.get_all_votes(query)

    def get_votes_by_meeting(self, meeting_id: str) -> List[Dict]:
        """Get all votes for a specific meeting"""
        query = VoteQuery(meeting_id=meeting_id)
        return self.get_all_votes(query)

    def get_votes_by_agenda_item(self, agenda_item: str) -> List[Dict]:
        """Get all votes for agenda items containing the search term"""
        query = VoteQuery(agenda_item=agenda_item)
        return self.get_all_votes(query)

    def get_votes_by_result(self, result: str) -> List[Dict]:
        """Get votes by result (passed/failed)"""
        query = VoteQuery(result=result)
        return self.get_all_votes(query)

    def get_councilmember_voting_record(self, councilmember: str) -> Dict:
        """Get comprehensive voting record for a councilmember"""
        votes = self.get_votes_by_councilmember(councilmember)

        if not votes:
            return {
                'councilmember': councilmember,
                'total_votes': 0,
                'votes': [],
                'summary': {'passed': 0, 'failed': 0, 'abstentions': 0}
            }

        # Count votes by result
        passed = len([v for v in votes if 'pass' in v['result'].lower()])
        failed = len([v for v in votes if 'fail' in v['result'].lower()])

        # Get individual vote details
        individual_votes = []
        for vote in votes:
            if vote['individual_votes']:
                for vote_detail in vote['individual_votes']:
                    if councilmember.lower() in vote_detail.get('name', '').lower():
                        individual_votes.append({
                            'vote_id': vote['id'],
                            'meeting_id': vote['meeting_id'],
                            'agenda_item': vote['agenda_item'],
                            'vote': vote_detail.get('vote', 'Unknown'),
                            'result': vote['result'],
                            'timestamp': vote['timestamp']
                        })

        return {
            'councilmember': councilmember,
            'total_votes': len(votes),
            'votes': individual_votes,
            'summary': {
                'passed': passed,
                'failed': failed,
                'abstentions': len([v for v in individual_votes if v['vote'].lower() in ['abstain', 'abstention']])
            }
        }

    def get_meeting_summary(self, meeting_id: str) -> Dict:
        """Get comprehensive summary for a meeting"""
        if meeting_id not in self.data['meetings']:
            return {'error': f'Meeting {meeting_id} not found'}

        meeting_data = self.data['meetings'][meeting_id]
        votes = self.get_votes_by_meeting(meeting_id)

        # Get agenda items with vote counts
        agenda_summary = {}
        for vote in votes:
            agenda_item = vote['agenda_item'] or 'Unknown'
            if agenda_item not in agenda_summary:
                agenda_summary[agenda_item] = {'total_votes': 0, 'passed': 0, 'failed': 0}

            agenda_summary[agenda_item]['total_votes'] += 1
            if 'pass' in vote['result'].lower():
                agenda_summary[agenda_item]['passed'] += 1
            else:
                agenda_summary[agenda_item]['failed'] += 1

        return {
            'meeting_id': meeting_id,
            'total_votes': meeting_data['total_votes'],
            'vote_results': meeting_data['vote_results'],
            'agenda_items': meeting_data['agenda_items'],
            'agenda_summary': agenda_summary,
            'votes': votes
        }

    def search_votes(self, search_term: str, search_fields: List[str] = None) -> List[Dict]:
        """Search votes by text in specified fields"""
        if search_fields is None:
            search_fields = ['agenda_item', 'motion_text']

        search_term = search_term.lower()
        matching_votes = []

        for vote in self.data['votes']:
            for field in search_fields:
                if vote.get(field) and search_term in str(vote[field]).lower():
                    matching_votes.append(vote)
                    break

        return matching_votes

    def get_statistics(self) -> Dict:
        """Get overall statistics about the vote data"""
        votes = self.data['votes']

        # Count by result
        passed = len([v for v in votes if 'pass' in v['result'].lower()])
        failed = len([v for v in votes if 'fail' in v['result'].lower()])

        # Count votes with individual data
        with_individual_votes = len([v for v in votes if v['individual_votes']])

        # Count votes with agenda items
        with_agenda_items = len([v for v in votes if v['agenda_item'] and 'Not available' not in str(v['agenda_item'])])

        return {
            'total_votes': len(votes),
            'total_meetings': len(self.data['meetings']),
            'total_councilmembers': len(self.data['councilmembers']),
            'total_agenda_items': len(self.data['agenda_items']),
            'vote_results': {
                'passed': passed,
                'failed': failed,
                'pass_rate': f"{(passed / len(votes) * 100):.1f}%" if votes else "0%"
            },
            'data_completeness': {
                'votes_with_individual_data': f"{(with_individual_votes / len(votes) * 100):.1f}%" if votes else "0%",
                'votes_with_agenda_items': f"{(with_agenda_items / len(votes) * 100):.1f}%" if votes else "0%"
            }
        }

    def get_available_councilmembers(self) -> List[str]:
        """Get list of all councilmembers who have voted"""
        return self.data['councilmembers']

    def get_available_meetings(self) -> List[str]:
        """Get list of all meeting IDs"""
        return list(self.data['meetings'].keys())

    def get_available_agenda_items(self) -> List[str]:
        """Get list of all agenda items"""
        return self.data['agenda_items']

# Example usage and testing
if __name__ == "__main__":
    # Initialize the query system
    query_system = TorranceVoteQuerySystem()

    # Get statistics
    stats = query_system.get_statistics()
    print("=== VOTE STATISTICS ===")
    print(json.dumps(stats, indent=2))

    # Get available data
    print(f"\n=== AVAILABLE DATA ===")
    print(f"Councilmembers: {query_system.get_available_councilmembers()}")
    print(f"Meetings: {query_system.get_available_meetings()}")
    print(f"Agenda items: {len(query_system.get_available_agenda_items())} items")

    # Example queries
    print(f"\n=== EXAMPLE QUERIES ===")

    # Get votes for a specific councilmember
    if query_system.get_available_councilmembers():
        cm = query_system.get_available_councilmembers()[0]
        cm_votes = query_system.get_votes_by_councilmember(cm)
        print(f"Votes for {cm}: {len(cm_votes)}")

    # Get votes for a specific meeting
    if query_system.get_available_meetings():
        meeting = query_system.get_available_meetings()[0]
        meeting_votes = query_system.get_votes_by_meeting(meeting)
        print(f"Votes for meeting {meeting}: {len(meeting_votes)}")

    # Search for votes
    search_results = query_system.search_votes("consent")
    print(f"Votes containing 'consent': {len(search_results)}")
