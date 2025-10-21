#!/bin/bash

# sync_static_deploy.sh
# Automatically syncs the latest data to static-deploy directory
# Ensures static-deploy always has complete and up-to-date data

set -e  # Exit on any error

echo "🔄 Syncing static-deploy directory with latest data..."

# Check if we're in the right directory
if [ ! -f "data/comprehensive_2025_results.json" ]; then
    echo "❌ Error: Must run from torrance-vote-viewer root directory"
    exit 1
fi

# Create static-deploy directories if they don't exist
mkdir -p static-deploy/data/backup

# Sync main data files
echo "📊 Syncing main data files..."
cp data/torrance_votes_smart_consolidated.json static-deploy/data/
cp data/torrance_votes_consolidated.json static-deploy/data/
cp data/comprehensive_2025_results.json static-deploy/data/
cp data/consolidated_votes_with_agenda.json static-deploy/data/

# Sync import data
echo "📥 Syncing import data..."
if [ -f "2025_meetings_import_data.json" ]; then
    cp 2025_meetings_import_data.json static-deploy/
fi

# Sync backup data
echo "💾 Syncing backup data..."
cp -r data/backup/* static-deploy/data/backup/ 2>/dev/null || true

# Verify sync
echo "✅ Verifying sync..."
echo "📊 Vote counts in static-deploy:"
echo "  - Import data: $(jq '.votes | length' static-deploy/2025_meetings_import_data.json 2>/dev/null || echo 'N/A') votes"
echo "  - Smart consolidated: $(jq '.votes | length' static-deploy/data/torrance_votes_smart_consolidated.json) votes"
echo "  - Consolidated: $(jq '.votes | length' static-deploy/data/torrance_votes_consolidated.json) votes"
echo "  - Comprehensive results: $(jq '.processing_summary.total_votes_extracted' static-deploy/data/comprehensive_2025_results.json) votes"

echo "🏛️ Meeting coverage:"
echo "  - Meetings in comprehensive results: $(jq '.processing_summary.completed_meetings' static-deploy/data/comprehensive_2025_results.json)"
echo "  - Meetings in smart consolidated: $(jq '.votes[].meeting_id' static-deploy/data/torrance_votes_smart_consolidated.json | sort -u | wc -l)"

echo "✅ Static-deploy sync completed successfully!"
echo "📁 Static-deploy directory is now up-to-date with latest data"
