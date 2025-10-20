# Torrance Vote Viewer

A comprehensive system for browsing and analyzing Torrance City Council votes with advanced querying capabilities.

## Overview

This system provides a clean, consolidated view of Torrance City Council voting data extracted from meeting videos. It includes 107 votes from 6 meetings with detailed information about agenda items, individual councilmember votes, and voting results.

## Data Structure

### Consolidated Data File
- **File**: `data/torrance_votes_consolidated.json`
- **Size**: ~90KB (optimized from original 276KB)
- **Votes**: 107 votes across 6 meetings
- **Councilmembers**: 7 members (Chen, Gerson, Kaji, Kalani, Lewis, Mattucci, Sheikh)
- **Agenda Items**: 31 unique agenda items

### Data Completeness
- **Votes with agenda items**: 100% (107/107)
- **Votes with individual councilmember data**: 4.7% (5/107)
- **Pass rate**: 92.5% (99 passed, 8 failed)

## Query System

The `vote_query_system.py` provides a comprehensive API for querying votes by various criteria:

### Core Query Functions

#### 1. Get All Votes
```python
from vote_query_system import TorranceVoteQuerySystem, VoteQuery

query_system = TorranceVoteQuerySystem()

# Get all votes
all_votes = query_system.get_all_votes()

# Get votes with filters
query = VoteQuery(
    councilmember="Chen",
    meeting_id="14510",
    result="passed",
    limit=10
)
filtered_votes = query_system.get_all_votes(query)
```

#### 2. Query by Councilmember
```python
# Get all votes for a specific councilmember
chen_votes = query_system.get_votes_by_councilmember("Chen")

# Get comprehensive voting record
chen_record = query_system.get_councilmember_voting_record("Chen")
```

#### 3. Query by Meeting
```python
# Get all votes for a meeting
meeting_votes = query_system.get_votes_by_meeting("14510")

# Get meeting summary
meeting_summary = query_system.get_meeting_summary("14510")
```

#### 4. Query by Agenda Item
```python
# Search votes by agenda item
consent_votes = query_system.get_votes_by_agenda_item("consent")
```

#### 5. Search Votes
```python
# Text search across multiple fields
search_results = query_system.search_votes("budget", ["agenda_item", "motion_text"])
```

### Vote Data Structure

Each vote contains the following information:

```json
{
  "id": "14510_5828",
  "meeting_id": "14510",
  "frame_number": 5828,
  "frame_path": "2025_meetings_data/votable_frames_14510/frame_005828.jpg",
  "timestamp": 1760796029.998416,
  "vote_tally": {
    "ayes": 7,
    "noes": 0,
    "abstentions": 0
  },
  "result": "Motion Passes",
  "confidence": "High",
  "agenda_item": "5. COUNCIL COMMITTEE MEETINGS AND ANNOUNCEMENTS",
  "motion_text": null,
  "individual_votes": [
    {
      "name": "Councilmember Gerson",
      "vote": "Yea"
    },
    {
      "name": "Councilmember Kaji",
      "vote": "Yea"
    }
  ]
}
```

### Available Data

#### Councilmembers
- Chen (Mayor)
- Gerson (Councilmember)
- Kaji (Councilmember)
- Kalani (Councilmember)
- Lewis (Councilmember)
- Mattucci (Councilmember)
- Sheikh (Councilmember)

#### Meetings
- 14490, 14510, 14524, 14530, 14536, 14538

#### Sample Agenda Items
- "5. COUNCIL COMMITTEE MEETINGS AND ANNOUNCEMENTS"
- "8. CONSENT CALENDAR"
- "10A. City Council Ad Hoc Naming of Public Facilities Committee"
- "10B. City Manager - Discuss and Provide Direction on Request for Subsidy"
- "14. ADJOURNMENT"

## Web Viewer Integration

### API Endpoints (Recommended)

For the web viewer, implement these REST API endpoints:

#### 1. Get Statistics
```
GET /api/statistics
```
Returns overall vote statistics and data completeness metrics.

#### 2. Search Votes
```
GET /api/votes?councilmember=Chen&meeting_id=14510&result=passed&limit=20
```
Query votes with multiple filters.

#### 3. Get Councilmember Record
```
GET /api/councilmember/{name}
```
Get comprehensive voting record for a councilmember.

#### 4. Get Meeting Summary
```
GET /api/meeting/{meeting_id}
```
Get all votes and summary for a specific meeting.

#### 5. Search by Text
```
GET /api/search?q=consent&fields=agenda_item,motion_text
```
Text search across vote fields.

### Frontend Features (Recommended)

1. **Dashboard**: Overview statistics and recent votes
2. **Councilmember View**: Individual voting records and patterns
3. **Meeting View**: Complete meeting breakdown with agenda items
4. **Search Interface**: Advanced filtering and text search
5. **Vote Details**: Individual vote information with frame references

## Data Sources and Links

### ✅ Complete Data Integration
- **Video Links**: ✅ Available for all meetings via Granicus player
- **Agenda Links**: ✅ Available for all meetings via Granicus agenda viewer
- **Meeting Dates**: ✅ Available for all meetings (2025 data)
- **Meeting Metadata**: ✅ Complete with titles, dates, and URLs

### Enhanced Features
1. **Static Web App**: Complete single-page application with routing
2. **Direct Links**: All votes link to source video and agenda
3. **Meeting Integration**: Full meeting context with metadata
4. **Responsive Design**: Mobile-friendly interface

## Static Web App Routes

The web app supports the following routes as requested:

### 🏛️ Meeting Routes
- **`baseurl.com/meeting/{clip_id}`** - View all votes for a specific meeting
  - Example: `baseurl.com/meeting/14510`
  - Shows meeting details, video link, agenda link, and all votes

- **`baseurl.com/meeting/{clip_id}/agenda_item/{id}`** - View votes for specific agenda item
  - Example: `baseurl.com/meeting/14510/agenda_item/consent_calendar_1`
  - Shows votes related to a specific agenda item

### 👥 Councilmember Routes
- **`baseurl.com/councilmember/{id}`** - View voting record for a councilmember
  - Example: `baseurl.com/councilmember/chen`
  - Shows individual voting history and statistics

### 📅 Year Routes
- **`baseurl.com/year/2025`** - View all meetings and votes for a year
  - Shows year overview with meeting list and statistics

### 🔍 Search Route
- **`baseurl.com/search`** - Advanced search interface
  - Search by text, councilmember, meeting, or result
  - Filter and browse votes with multiple criteria

## File Organization

```
torrance-vote-viewer/
├── data/
│   ├── torrance_votes_enhanced.json        # Enhanced data with metadata
│   ├── torrance_votes_consolidated.json    # Original consolidated data
│   ├── consolidated_votes_with_agenda.json  # Source data
│   ├── comprehensive_2025_results.json      # Processing summary
│   └── backup/                             # Archived duplicate files
├── index.html                              # Static web app
├── server.py                               # Development server
├── vote_query_system.py                    # Query API
├── web_api.py                              # Flask API (optional)
├── requirements.txt                        # Python dependencies
└── README.md                               # This file
```

## Quick Start

### 🚀 Run the Static Web App
```bash
# Start the development server
python3 server.py

# Open your browser to:
# http://localhost:8000
```

### 📱 Access the Routes
- **Home**: `http://localhost:8000/`
- **Meetings**: `http://localhost:8000/#/meetings`
- **Specific Meeting**: `http://localhost:8000/#/meeting/14510`
- **Councilmember**: `http://localhost:8000/#/councilmember/chen`
- **Year View**: `http://localhost:8000/#/year/2025`
- **Search**: `http://localhost:8000/#/search`

### 🌐 Deploy to Production
The app is a static web application that can be deployed to any web server:

1. **Upload files** to your web server:
   - `index.html` (main app)
   - `data/torrance_votes_enhanced.json` (data file)
   - `server.py` (optional, for Python hosting)

2. **Configure web server** to serve `index.html` for all routes (SPA routing)

3. **Set up HTTPS** for production use

## Usage Examples

### Python API Usage
```python
from vote_query_system import TorranceVoteQuerySystem

# Initialize
query_system = TorranceVoteQuerySystem()

# Get statistics
stats = query_system.get_statistics()
print(f"Total votes: {stats['total_votes']}")
print(f"Pass rate: {stats['vote_results']['pass_rate']}")

# Find votes by councilmember
chen_votes = query_system.get_votes_by_councilmember("Chen")
print(f"Chen voted on {len(chen_votes)} items")

# Search for specific topics
budget_votes = query_system.search_votes("budget")
print(f"Found {len(budget_votes)} budget-related votes")
```

### Web Integration Example
```javascript
// Fetch vote statistics
fetch('/api/statistics')
  .then(response => response.json())
  .then(stats => {
    console.log(`Total votes: ${stats.total_votes}`);
    console.log(`Pass rate: ${stats.vote_results.pass_rate}`);
  });

// Search votes
fetch('/api/votes?councilmember=Chen&result=passed')
  .then(response => response.json())
  .then(votes => {
    votes.forEach(vote => {
      console.log(`Vote ${vote.id}: ${vote.result}`);
    });
  });
```

## Future Enhancements

1. **Real-time Updates**: Add new meeting data as it becomes available
2. **Advanced Analytics**: Voting patterns, coalition analysis, issue tracking
3. **Export Features**: CSV, PDF reports for specific queries
4. **Visualization**: Charts and graphs for voting patterns
5. **Mobile Interface**: Responsive design for mobile access

## Technical Notes

- **Data Format**: JSON with standardized structure
- **Query Performance**: Optimized for fast lookups and filtering
- **Storage**: Reduced from 276KB to 90KB through deduplication
- **Compatibility**: Python 3.6+ for query system
- **Extensibility**: Easy to add new query methods and filters
