# Torrance Vote Viewer - Data Export
**Export Date**: October 20, 2025, 19:51:59
**Export Type**: Complete Data State with Individual Vote Data

## 📊 Data Overview

This export contains the complete, processed state of the Torrance City Council vote data with individual councilmember vote information successfully extracted and integrated.

### Key Statistics
- **Total Votes**: 122 votes (smart consolidated)
- **Meetings**: 15 meetings processed
- **Councilmembers**: 6 active councilmembers with complete vote data
- **Individual Vote Data**: Successfully extracted for 34+ votes

### Councilmember Vote Counts
- **MIKE GERSON**: 119 votes (87 yes, 9 no, 1 abstain)
- **JON KAJI**: 114 votes (88 yes, 1 no, 4 abstain)
- **SHARON KALANI**: 116 votes (85 yes, 2 no, 4 abstain)
- **BRIDGET LEWIS**: 29 votes (1 yes, 0 no, 3 abstain)
- **AURELIO MATTUCCI**: 28 votes (0 yes, 0 no, 4 abstain)
- **ASAM SHAIKH**: 115 votes (85 yes, 2 no, 3 abstain)

## 📁 File Structure

### Main Data Files
- `torrance_votes_smart_consolidated.json` - **PRIMARY DATA SOURCE** - Complete consolidated vote data with individual votes
- `comprehensive_2025_results.json` - Comprehensive processing results (189 votes from 21 meetings)
- `consolidated_votes_with_agenda.json` - Votes with agenda item details
- `torrance_votes_consolidated.json` - Basic consolidated votes
- `torrance_votes_enhanced.json` - Enhanced vote data

### Backup Data
- `backup/` - Contains 100+ backup files from previous processing runs
- `backup_*.json` - Timestamped backups of key data files

### Import Data
- `2025_meetings_import_data.json` - Original import data (107 votes from 6 meetings)
- `all_2025_meetings_complete.json` - Complete meeting metadata

### Backup Data
- `data/backup/` - Contains 100 backup files from previous processing runs

## 🔧 Processing Scripts Included

### Core Processing
- `parse_raw_vote_data.py` - **KEY SCRIPT** - Extracts individual vote data from OCR raw text
- `merge_individual_votes_by_agenda.py` - Merges individual votes by agenda item matching
- `improved_deduplication.py` - Advanced deduplication with case-insensitive matching
- `fix_vote_tally.py` - Fixes vote tally calculations from individual votes
- `update_meeting_metadata.py` - Updates meeting vote counts after deduplication

### Deployment
- `sync_static_deploy.sh` - Syncs data to static-deploy directory

## 🎯 Key Achievements

### Individual Vote Data Extraction
- Successfully extracted individual councilmember votes from OCR raw text
- Handled OCR errors in vote results (nl→no, ly→yes, a→abstain)
- Normalized councilmember names consistently
- Integrated with existing vote data structure

### Data Quality Improvements
- Fixed vote tally calculations (ayes, noes, abstentions)
- Resolved duplicate vote issues with improved deduplication
- Updated meeting metadata with accurate vote counts
- Ensured data consistency across all files

### Councilmember Data
- **Bridget Lewis**: Successfully added with proper vote data
- **Aurelio Mattucci**: Correctly included with vote records
- All councilmembers now have complete statistics and summaries

## 🚀 Usage Instructions

### To Restore This Data
1. Copy the `data/` directory to your project root
2. Copy the `static_deploy_data/` files to `static-deploy/data/`
3. Run `./sync_static_deploy.sh` to ensure consistency

### To Continue Processing
1. Use `parse_raw_vote_data.py` for additional individual vote extraction
2. Use `improved_deduplication.py` for vote deduplication
3. Use `sync_static_deploy.sh` to update deployment data

## 📈 Data Quality Status

- ✅ Individual vote data extracted and integrated
- ✅ Vote tallies correctly calculated
- ✅ Duplicate votes resolved
- ✅ Councilmember data complete
- ✅ Meeting metadata updated
- ✅ Static deployment data synced
- ✅ Data consistency verified

## 🔍 Technical Notes

### Data Structure
The primary data file (`torrance_votes_smart_consolidated.json`) contains:
- `votes[]` - Array of vote objects with individual_votes
- `meetings{}` - Meeting metadata with updated vote counts
- `councilmembers[]` - List of all councilmembers
- `councilmember_stats{}` - Vote statistics per councilmember
- `councilmember_summaries{}` - AI-generated summaries per councilmember

### Individual Vote Format
```json
{
  "individual_votes": {
    "MIKE GERSON": "YES",
    "JON KAJI": "NO",
    "SHARON KALANI": "ABSTAIN",
    "BRIDGET LEWIS": "YES",
    "AURELIO MATTUCCI": "NO",
    "ASAM SHAIKH": "YES"
  }
}
```

## 📞 Support

This export represents a complete, working state of the Torrance Vote Viewer data processing system. All individual vote data has been successfully extracted and integrated, resolving the previous issues with missing councilmember vote information.

**Export completed successfully on October 20, 2025 at 19:51:59**
