# Bulletproof Import System for Torrance Vote Viewer

## 🚀 Overview

The Bulletproof Import System is a comprehensive solution for importing new meeting data into the Torrance Vote Viewer. It addresses all the issues we've encountered and provides robust, production-ready data processing.

## ✨ Features

### 🔄 **Advanced Deduplication**
- **Smart Vote Consolidation**: Groups votes by `meeting_id` + `agenda_item`
- **Frame Number Analysis**: Uses frame numbers to determine vote sequence
- **Individual Vote Merging**: Combines individual councilmember votes from duplicate entries
- **Consolidation Tracking**: Maintains audit trail of consolidated votes

### 🎯 **Meta ID Mapping & Timestamps**
- **Automatic Scraping**: Scrapes Granicus player pages for meta IDs
- **Intelligent Matching**: Maps agenda items to video chapters using text similarity
- **Accurate Timestamps**: Extracts precise video timestamps for deep linking
- **Retry Logic**: Handles network failures with exponential backoff

### 📊 **Meeting Summarization**
- **Gemini API Integration**: Generates AI-powered meeting summaries
- **Vote Analysis**: Analyzes voting patterns and outcomes
- **Key Item Extraction**: Identifies important agenda items
- **Professional Formatting**: Creates readable, informative summaries

### 🛡️ **Data Validation & Integrity**
- **Structure Validation**: Validates required fields and data types
- **Consistency Checks**: Ensures data consistency across meetings
- **Error Reporting**: Detailed error messages with context
- **Backup Creation**: Automatic backups before data changes

### 📝 **Comprehensive Logging**
- **Multi-level Logging**: DEBUG, INFO, WARNING, ERROR levels
- **File + Console**: Logs to both file and console
- **Import Statistics**: Tracks processing metrics
- **Error Tracking**: Maintains error history

## 🛠️ Installation

### Prerequisites
```bash
pip install requests beautifulsoup4
```

### Setup
1. **Clone the repository** (if not already done)
2. **Set up environment variables**:
   ```bash
   export GEMINI_API_KEY="your_gemini_api_key_here"
   ```
3. **Create required directories**:
   ```bash
   mkdir -p data logs
   ```

## 📖 Usage

### Basic Usage

```bash
# Dry run (no changes saved)
python bulletproof_import.py --input new_meeting_data.json --dry-run

# Full import
python bulletproof_import.py --input new_meeting_data.json

# Verbose output
python bulletproof_import.py --input new_meeting_data.json --verbose

# With Gemini API key
python bulletproof_import.py --input new_meeting_data.json --gemini-key YOUR_API_KEY
```

### Advanced Usage

```bash
# Custom output file
python bulletproof_import.py --input new_meeting_data.json --output custom_output.json

# Batch processing multiple files
for file in data/new_meetings/*.json; do
    python bulletproof_import.py --input "$file"
done
```

### Programmatic Usage

```python
from bulletproof_import import BulletproofImporter, ImportConfig

# Create configuration
config = ImportConfig(
    input_file='new_meeting_data.json',
    dry_run=False,
    verbose=True,
    gemini_api_key='your_api_key'
)

# Run import
importer = BulletproofImporter(config)
importer.run_import()
```

## 📁 Input Data Format

### Required Structure
```json
{
  "votes": [
    {
      "id": "14520_1",
      "meeting_id": "14520",
      "agenda_item": "1. Call to Order",
      "frame_number": 1,
      "individual_votes": {
        "GEORGE CHEN": "YES",
        "MIKE GERSON": "YES",
        "JONATHAN KANG": "YES",
        "SHARON KALANI": "YES",
        "ASAM SHAIKH": "YES"
      }
    }
  ],
  "meetings": {
    "14520": {
      "id": "14520",
      "title": "City Council Meeting",
      "date": "2025-01-15",
      "time": "19:00",
      "video_url": "https://torrance.granicus.com/player/clip/14520",
      "agenda_url": "https://torrance.granicus.com/ViewPublisher.php?view_id=2&clip_id=14520"
    }
  }
}
```

### Optional Fields
- `meta_id`: Pre-existing meta ID for video chapter
- `video_timestamp`: Pre-existing video timestamp
- `timestamp_estimated`: Whether timestamp is estimated (default: true)

## 🔧 Configuration

### Environment Variables
```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
export LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR
```

### Configuration File
Edit `import_config.py` to customize:
- API settings
- Scraping parameters
- Validation rules
- Logging preferences

## 📊 Output

### Consolidated Data Structure
```json
{
  "votes": [
    {
      "meeting_id": "14520",
      "agenda_item": "1. Call to Order",
      "frame_number": 1,
      "individual_votes": {
        "GEORGE CHEN": "YES",
        "MIKE GERSON": "YES"
      },
      "meta_id": "12345",
      "video_timestamp": 120,
      "timestamp_estimated": false,
      "consolidated_from": ["14520_1", "14520_1_dup"]
    }
  ],
  "meetings": {
    "14520": {
      "id": "14520",
      "title": "City Council Meeting",
      "date": "2025-01-15",
      "time": "19:00",
      "video_url": "https://torrance.granicus.com/player/clip/14520",
      "agenda_url": "https://torrance.granicus.com/ViewPublisher.php?view_id=2&clip_id=14520"
    }
  },
  "meeting_summaries": {
    "14520": {
      "summary": "City Council meeting with 15 votes recorded...",
      "total_votes": 15,
      "passed_votes": 12,
      "failed_votes": 3,
      "key_items": ["Budget Approval", "Zoning Change", "Public Safety"],
      "generated_at": "2025-01-15T20:30:00"
    }
  },
  "councilmember_stats": {
    "GEORGE CHEN": {
      "total_votes": 15,
      "yes_votes": 12,
      "no_votes": 2,
      "abstentions": 1
    }
  },
  "last_updated": "2025-01-15T20:30:00"
}
```

## 📈 Import Statistics

The script provides detailed statistics:
```
=== IMPORT STATISTICS ===
Meetings processed: 3
Votes processed: 45
Duplicates found: 12
Meta IDs mapped: 38
Timestamps extracted: 35
Summaries generated: 3
Errors encountered: 0
```

## 🚨 Error Handling

### Common Issues & Solutions

1. **Network Errors**:
   - Automatic retry with exponential backoff
   - Graceful degradation if scraping fails
   - Detailed error logging

2. **Data Validation Errors**:
   - Clear error messages with field names
   - Continues processing valid data
   - Reports all validation issues

3. **API Errors**:
   - Handles rate limiting
   - Falls back to basic summaries
   - Logs API errors for debugging

### Error Recovery
- **Automatic Backups**: Created before each import
- **Rollback Capability**: Can restore from backup
- **Partial Success**: Processes valid data even if some fails

## 🔍 Debugging

### Enable Debug Logging
```bash
python bulletproof_import.py --input data.json --verbose
```

### Check Log Files
```bash
tail -f import_log.txt
```

### Validate Existing Data
```python
from sample_usage import validate_existing_data
validate_existing_data()
```

## 🧪 Testing

### Run Sample Import
```python
from sample_usage import create_sample_data, run_dry_run_import

# Create sample data
create_sample_data()

# Run dry-run import
run_dry_run_import()
```

### Test Individual Components
```python
from bulletproof_import import BulletproofImporter, ImportConfig

# Test deduplication
config = ImportConfig(input_file='test_data.json', dry_run=True)
importer = BulletproofImporter(config)
# ... test specific methods
```

## 🔄 Workflow Integration

### Automated Import Pipeline
```bash
#!/bin/bash
# automated_import.sh

# Download new meeting data
curl -o new_meeting.json "https://api.torrance.gov/meetings/latest"

# Run import
python bulletproof_import.py --input new_meeting.json

# Deploy updated data
git add data/torrance_votes_smart_consolidated.json
git commit -m "Import new meeting data"
git push origin main
```

### CI/CD Integration
```yaml
# .github/workflows/import.yml
name: Import New Meeting Data
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  import:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install requests beautifulsoup4
      - name: Run import
        run: python bulletproof_import.py --input new_meeting.json
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

## 📚 API Reference

### BulletproofImporter Class

#### Methods
- `load_existing_data()`: Load current consolidated data
- `deduplicate_votes(votes)`: Remove duplicate votes
- `scrape_meta_ids_and_timestamps(meeting_id)`: Extract video metadata
- `map_meta_ids_to_votes(votes, meeting_id)`: Match votes to video chapters
- `generate_meeting_summary(meeting_id, votes)`: Create AI summary
- `validate_data_integrity(data)`: Check data quality
- `merge_with_existing_data(new_votes, new_meetings)`: Combine datasets
- `save_data(data)`: Write processed data to file

### ImportConfig Class

#### Parameters
- `input_file`: Path to input JSON file
- `output_file`: Path to output JSON file
- `dry_run`: Whether to run without saving changes
- `verbose`: Enable detailed logging
- `gemini_api_key`: API key for summary generation
- `max_retries`: Maximum retry attempts for network requests
- `retry_delay`: Delay between retry attempts
- `timeout`: Request timeout in seconds

## 🤝 Contributing

### Adding New Features
1. **Extend ImportConfig**: Add new configuration options
2. **Update BulletproofImporter**: Implement new processing logic
3. **Add Tests**: Create test cases for new functionality
4. **Update Documentation**: Document new features

### Reporting Issues
1. **Check Logs**: Review `import_log.txt` for error details
2. **Provide Sample Data**: Include problematic input data
3. **Describe Expected Behavior**: What should happen vs. what happens
4. **Include Environment**: Python version, OS, dependencies

## 📄 License

This import system is part of the Torrance Vote Viewer project and follows the same license terms.

## 🆘 Support

For issues or questions:
1. **Check the logs**: `import_log.txt`
2. **Run validation**: `python sample_usage.py` → `validate_existing_data()`
3. **Test with sample data**: Use `create_sample_data()` and `run_dry_run_import()`
4. **Review configuration**: Check `import_config.py` settings

---

**🎯 This bulletproof import system ensures reliable, accurate, and comprehensive data processing for the Torrance Vote Viewer!**
