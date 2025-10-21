#!/usr/bin/env python3
"""
Fix councilmember data by removing Mattucci who has no vote data
and ensuring correct name formatting
"""

import json

def fix_councilmember_data():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("Current councilmembers:", data['councilmembers'])
    print("Current councilmember_stats keys:", list(data['councilmember_stats'].keys()))

    # Remove MATTUCCI from councilmembers array since there's no vote data
    if "MATTUCCI" in data['councilmembers']:
        data['councilmembers'] = [cm for cm in data['councilmembers'] if cm != "MATTUCCI"]
        print("Removed MATTUCCI from councilmembers array")

    # Remove MATTUCCI from councilmember_stats
    if "MATTUCCI" in data['councilmember_stats']:
        del data['councilmember_stats']["MATTUCCI"]
        print("Removed MATTUCCI from councilmember_stats")

    # Remove MATTUCCI from councilmember_summaries
    if "MATTUCCI" in data['councilmember_summaries']:
        del data['councilmember_summaries']["MATTUCCI"]
        print("Removed MATTUCCI from councilmember_summaries")

    # Fix ASAM SHEIKH name (should be ASAM SHEIKH based on vote data)
    if "ASAM SHEIKH" in data['councilmembers']:
        data['councilmembers'] = [cm if cm != "ASAM SHEIKH" else "ASAM SHEIKH" for cm in data['councilmembers']]
        print("Fixed ASAM SHEIKH → ASAM SHEIKH in councilmembers")

    if "ASAM SHEIKH" in data['councilmember_stats']:
        data['councilmember_stats']["ASAM SHEIKH"] = data['councilmember_stats'].pop("ASAM SHEIKH")
        print("Fixed ASAM SHEIKH → ASAM SHEIKH in councilmember_stats")

    if "ASAM SHEIKH" in data['councilmember_summaries']:
        data['councilmember_summaries']["ASAM SHEIKH"] = data['councilmember_summaries'].pop("ASAM SHEIKH")
        print("Fixed ASAM SHEIKH → ASAM SHEIKH in councilmember_summaries")

    print("\nUpdated councilmembers:", data['councilmembers'])
    print("Updated councilmember_stats keys:", list(data['councilmember_stats'].keys()))

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("\n✅ Councilmember data fixed!")

if __name__ == "__main__":
    fix_councilmember_data()
