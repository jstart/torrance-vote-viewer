#!/usr/bin/env python3
"""
Fix councilmember data structure issues:
1. Update councilmembers array to match councilmember_stats keys
2. Ensure proper name mapping for frontend display
"""

import json
import sys
from typing import Dict, List, Any

def fix_councilmember_data(data_file: str):
    """Fix councilmember data structure"""
    print(f"🔧 Fixing councilmember data in {data_file}...")
    
    # Load the data
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Get the actual councilmember names from stats
    councilmember_stats = data.get('councilmember_stats', {})
    actual_councilmembers = list(councilmember_stats.keys())
    
    print(f"📊 Found {len(actual_councilmembers)} councilmembers in stats:")
    for cm in actual_councilmembers:
        stats = councilmember_stats[cm]
        print(f"  - {cm}: {stats['total_votes']} votes ({stats['yes_votes']} yes, {stats['no_votes']} no)")
    
    # Update the councilmembers array to match the stats keys
    data['councilmembers'] = actual_councilmembers
    
    # Save the fixed data
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"🎉 Updated councilmembers array to match stats keys")
    print(f"📄 Updated file: {data_file}")

if __name__ == "__main__":
    data_file = "data/torrance_votes_smart_consolidated.json"
    fix_councilmember_data(data_file)
