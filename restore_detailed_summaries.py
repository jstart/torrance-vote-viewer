#!/usr/bin/env python3
"""
Restore detailed councilmember summaries from backup
"""

import json

def restore_detailed_summaries():
    """Restore detailed councilmember summaries from backup"""
    
    # Load current data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        current_data = json.load(f)
    
    # Load backup data
    with open('data/torrance_votes_smart_consolidated_backup.json', 'r') as f:
        backup_data = json.load(f)
    
    print("Restoring detailed councilmember summaries...")
    
    # Get current councilmembers
    current_councilmembers = current_data.get('councilmembers', [])
    print(f"Current councilmembers: {current_councilmembers}")
    
    # Get backup summaries
    backup_summaries = backup_data.get('councilmember_summaries', {})
    print(f"Backup summaries available for: {list(backup_summaries.keys())}")
    
    # Name mapping for councilmembers
    name_mapping = {
        'AURELIO MATTUCCI': 'MATTUCCI',
        'BRIDGET LEWIS': 'BRIDGET LEWIS',  # No backup available
        'ASAM SHEIKH': 'ASAM SHEIKH',
        'JON KAJI': 'JON KAJI',
        'MIKE GERSON': 'MIKE GERSON',
        'SHARON KALANI': 'SHARON KALANI'
    }
    
    # Restore detailed summaries for current councilmembers
    restored_count = 0
    for councilmember in current_councilmembers:
        backup_name = name_mapping.get(councilmember, councilmember)
        
        if backup_name in backup_summaries:
            # Update the summary with detailed information
            current_data['councilmember_summaries'][councilmember] = backup_summaries[backup_name]
            restored_count += 1
            print(f"  ✅ Restored detailed summary for {councilmember} (from {backup_name})")
        else:
            print(f"  ❌ No detailed summary found for {councilmember} (looked for {backup_name})")
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(current_data, f, indent=2)
    
    print(f"\n✅ Restored {restored_count} detailed councilmember summaries!")
    
    # Show sample of restored data
    sample_councilmember = current_councilmembers[0] if current_councilmembers else None
    if sample_councilmember and sample_councilmember in current_data['councilmember_summaries']:
        summary = current_data['councilmember_summaries'][sample_councilmember]
        print(f"\n📋 Sample restored summary for {sample_councilmember}:")
        print(f"  Summary: {summary.get('summary', 'N/A')[:100]}...")
        print(f"  Bio URL: {summary.get('bio_url', 'N/A')}")
        print(f"  Policy Focus: {summary.get('policy_focus', [])}")

if __name__ == "__main__":
    restore_detailed_summaries()
