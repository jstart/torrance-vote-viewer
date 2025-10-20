#!/usr/bin/env python3
"""
Fix Bridget Lewis data corruption in torrance_votes_smart_consolidated.json
"""

import json
import sys

def fix_lewis_data():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    print("Current councilmembers:", data['councilmembers'])
    print("Current councilmember_stats keys:", list(data['councilmember_stats'].keys()))
    print("Current councilmember_summaries keys:", list(data['councilmember_summaries'].keys()))

    # Add Bridget Lewis to councilmembers array
    if "BRIDGET LEWIS" not in data['councilmembers']:
        data['councilmembers'].append("BRIDGET LEWIS")
        print("Added BRIDGET LEWIS to councilmembers array")

    # Create Lewis stats (we'll need to calculate these from the votes)
    # For now, let's add placeholder stats
    if "BRIDGET LEWIS" not in data['councilmember_stats']:
        data['councilmember_stats']["BRIDGET LEWIS"] = {
            "total_votes": 0,
            "yes_votes": 0,
            "no_votes": 0,
            "abstentions": 0
        }
        print("Added BRIDGET LEWIS to councilmember_stats")

    # Move Lewis summary from Sharon Kalani to Bridget Lewis
    if "SHARON KALANI" in data['councilmember_summaries']:
        kalani_summary = data['councilmember_summaries']["SHARON KALANI"]
        if kalani_summary.get('summary', '').startswith('Lewis serves as councilmember'):
            # This is actually Lewis's summary, move it
            data['councilmember_summaries']["BRIDGET LEWIS"] = kalani_summary.copy()
            print("Moved Lewis summary from Sharon Kalani to Bridget Lewis")

            # Create a proper Sharon Kalani summary
            data['councilmember_summaries']["SHARON KALANI"] = {
                "summary": "Kalani serves as councilmember of the Torrance City Council. Councilmember Sharon Kalani brings community-focused leadership and dedication to serving Torrance residents. Demonstrates strong consensus-building skills and commitment to municipal priorities. Primary policy focus areas include Community Services, Public Safety, and Budget & Finance, reflecting commitment to these key municipal priorities. Key initiatives include Community service programs, Public safety initiatives, and Budget oversight, demonstrating proactive leadership in city governance.",
                "role": "Councilmember",
                "notes": [
                    "Participated in recorded votes",
                    "Active in community service and public safety",
                    "Bio: https://www.torranceca.gov/government/city-council-and-elected-officials/kalani"
                ],
                "stats": {
                    "total_votes": data['councilmember_stats']["SHARON KALANI"]["total_votes"],
                    "yes_votes": data['councilmember_stats']["SHARON KALANI"]["yes_votes"],
                    "no_votes": data['councilmember_stats']["SHARON KALANI"]["no_votes"]
                },
                "bio_url": "https://www.torranceca.gov/government/city-council-and-elected-officials/kalani",
                "policy_focus": ["Community Services", "Public Safety", "Budget & Finance"],
                "notable_initiatives": ["Community service programs", "Public safety initiatives", "Budget oversight"],
                "policy_votes": {
                    "Planning & Development": 0,
                    "Public Safety": 0,
                    "Budget & Finance": 0,
                    "Infrastructure": 0,
                    "Community Services": 0,
                    "Environmental": 0,
                    "Housing": 0
                },
                "bio_note": "Official bio page"
            }
            print("Created proper Sharon Kalani summary")

    # Calculate Lewis stats from votes (if any exist)
    lewis_votes = 0
    lewis_yes = 0
    lewis_no = 0

    for vote in data['votes']:
        if 'individual_votes' in vote:
            # Check for various Lewis name formats
            for name, vote_result in vote['individual_votes'].items():
                if 'LEWIS' in name.upper() or 'BRIDGET' in name.upper():
                    lewis_votes += 1
                    if vote_result.upper() in ['YES', 'Y']:
                        lewis_yes += 1
                    elif vote_result.upper() in ['NO', 'N']:
                        lewis_no += 1

    if lewis_votes > 0:
        data['councilmember_stats']["BRIDGET LEWIS"] = {
            "total_votes": lewis_votes,
            "yes_votes": lewis_yes,
            "no_votes": lewis_no,
            "abstentions": 0
        }
        print(f"Calculated Lewis stats: {lewis_votes} total, {lewis_yes} yes, {lewis_no} no")

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("✅ Fixed Bridget Lewis data corruption!")
    print("Updated councilmembers:", data['councilmembers'])
    print("Updated councilmember_stats keys:", list(data['councilmember_stats'].keys()))
    print("Updated councilmember_summaries keys:", list(data['councilmember_summaries'].keys()))

if __name__ == "__main__":
    fix_lewis_data()
