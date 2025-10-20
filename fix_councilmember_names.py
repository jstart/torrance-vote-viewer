#!/usr/bin/env python3
"""
Fix councilmember name formatting issues
- Change BRIDGET LEWIS to Bridget Lewis
- Change MATTUCCI to Aurelio Mattucci
"""

import json
import sys

def fix_councilmember_names():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("Current councilmembers:", data['councilmembers'])

    # Fix Bridget Lewis name formatting
    if "BRIDGET LEWIS" in data['councilmembers']:
        # Update councilmembers array
        data['councilmembers'] = [name.replace("BRIDGET LEWIS", "Bridget Lewis") for name in data['councilmembers']]
        print("✅ Fixed BRIDGET LEWIS → Bridget Lewis in councilmembers array")

        # Update councilmember_stats
        if "BRIDGET LEWIS" in data['councilmember_stats']:
            data['councilmember_stats']["Bridget Lewis"] = data['councilmember_stats']["BRIDGET LEWIS"]
            del data['councilmember_stats']["BRIDGET LEWIS"]
            print("✅ Fixed BRIDGET LEWIS → Bridget Lewis in councilmember_stats")

        # Update councilmember_summaries
        if "BRIDGET LEWIS" in data['councilmember_summaries']:
            data['councilmember_summaries']["Bridget Lewis"] = data['councilmember_summaries']["BRIDGET LEWIS"]
            del data['councilmember_summaries']["BRIDGET LEWIS"]
            print("✅ Fixed BRIDGET LEWIS → Bridget Lewis in councilmember_summaries")

    # Fix Mattucci name formatting
    if "MATTUCCI" in data['councilmembers']:
        # Update councilmembers array
        data['councilmembers'] = [name.replace("MATTUCCI", "Aurelio Mattucci") for name in data['councilmembers']]
        print("✅ Fixed MATTUCCI → Aurelio Mattucci in councilmembers array")

        # Update councilmember_stats
        if "MATTUCCI" in data['councilmember_stats']:
            data['councilmember_stats']["Aurelio Mattucci"] = data['councilmember_stats']["MATTUCCI"]
            del data['councilmember_stats']["MATTUCCI"]
            print("✅ Fixed MATTUCCI → Aurelio Mattucci in councilmember_stats")

        # Update councilmember_summaries
        if "MATTUCCI" in data['councilmember_summaries']:
            data['councilmember_summaries']["Aurelio Mattucci"] = data['councilmember_summaries']["MATTUCCI"]
            del data['councilmember_summaries']["MATTUCCI"]
            print("✅ Fixed MATTUCCI → Aurelio Mattucci in councilmember_summaries")

    # Update individual votes to use correct names
    votes_updated = 0
    for vote in data['votes']:
        if 'individual_votes' in vote:
            # Fix Bridget Lewis in individual votes
            if "BRIDGET LEWIS" in vote['individual_votes']:
                vote['individual_votes']["Bridget Lewis"] = vote['individual_votes']["BRIDGET LEWIS"]
                del vote['individual_votes']["BRIDGET LEWIS"]
                votes_updated += 1

            # Fix Mattucci in individual votes
            if "MATTUCCI" in vote['individual_votes']:
                vote['individual_votes']["Aurelio Mattucci"] = vote['individual_votes']["MATTUCCI"]
                del vote['individual_votes']["MATTUCCI"]
                votes_updated += 1

    if votes_updated > 0:
        print(f"✅ Updated {votes_updated} votes with corrected names")

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("✅ Fixed councilmember name formatting!")
    print("Updated councilmembers:", data['councilmembers'])
    print("Updated councilmember_stats keys:", list(data['councilmember_stats'].keys()))
    print("Updated councilmember_summaries keys:", list(data['councilmember_summaries'].keys()))

if __name__ == "__main__":
    fix_councilmember_names()
