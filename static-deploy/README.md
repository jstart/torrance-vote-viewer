# Static-Deploy Data Directory

This directory contains the complete and up-to-date data for the Torrance Vote Viewer application.

## 📊 Data Files Overview

### Main Data Files
- **`2025_meetings_import_data.json`** - 107 votes from 6 meetings (raw import data)
- **`data/torrance_votes_smart_consolidated.json`** - 68 votes (deduplicated, optimized)
- **`data/torrance_votes_consolidated.json`** - 107 votes (all votes, no deduplication)
- **`data/consolidated_votes_with_agenda.json`** - 107 votes (organized by agenda items)
- **`data/comprehensive_2025_results.json`** - 189 votes from 21 meetings (processing results)

### Backup Data
- **`data/backup/`** - Individual meeting summary files and vote data

## 🔄 Keeping Data Up-to-Date

### Automatic Sync
Run the sync script to update static-deploy with latest data:
```bash
./sync_static_deploy.sh
```

### Manual Sync
If you need to manually sync specific files:
```bash
# Copy main data files
cp data/torrance_votes_smart_consolidated.json static-deploy/data/
cp data/torrance_votes_consolidated.json static-deploy/data/
cp data/comprehensive_2025_results.json static-deploy/data/
cp data/consolidated_votes_with_agenda.json static-deploy/data/

# Copy import data
cp 2025_meetings_import_data.json static-deploy/

# Copy backup data
cp -r data/backup/* static-deploy/data/backup/
```

## 📈 Data Consistency

### Vote Counts Explained
- **107 votes** - Raw vote data from 6 meetings (no deduplication)
- **68 votes** - Smart consolidated data (deduplicated for better UX)
- **189 votes** - Comprehensive results from all 21 processed meetings

### Meeting Coverage
- **6 meetings** in consolidated data: 14490, 14510, 14524, 14530, 14536, 14538
- **21 meetings** in comprehensive results (includes all processed meetings)

## 🚀 Deployment

This directory is designed for static deployment. All data files are self-contained and ready for production use.

## ⚠️ Important Notes

1. **Always run sync script** after updating main data files
2. **Verify vote counts** match expected values after sync
3. **Check meeting coverage** to ensure no data is missing
4. **Backup data** is automatically included in sync

## 🔍 Troubleshooting

If vote counts seem inconsistent:
1. Check if deduplication was applied (smart vs regular consolidated)
2. Verify all meetings are included in comprehensive results
3. Run sync script to ensure latest data is copied
4. Check backup directory for individual meeting data
