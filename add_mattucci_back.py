#!/usr/bin/env python3
"""
Add Aurelio Mattucci back to councilmembers with 0 votes
"""

import json

def add_mattucci_back():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    # Add Aurelio Mattucci to councilmembers list
    if 'AURELIO MATTUCCI' not in data['councilmembers']:
        data['councilmembers'].append('AURELIO MATTUCCI')
        print("✅ Added AURELIO MATTUCCI to councilmembers list")

    # Add Aurelio Mattucci to councilmember_stats with 0 votes
    data['councilmember_stats']['AURELIO MATTUCCI'] = {
        "total_votes": 0,
        "yes_votes": 0,
        "no_votes": 0,
        "abstentions": 0
    }
    print("✅ Added AURELIO MATTUCCI to councilmember_stats with 0 votes")

    # Add Aurelio Mattucci summary
    data['councilmember_summaries']['AURELIO MATTUCCI'] = {
        "summary": "Mattucci serves as councilmember of the Torrance City Council. Councilmember Aurelio Mattucci is dedicated to maintaining Torrance's character while supporting responsible growth and development. Demonstrates commitment to community engagement and fiscal responsibility. Primary policy focus areas include Planning & Development, Public Safety, and Budget & Finance. Key initiatives include Development oversight, Public safety initiatives, and Budget management. Learn more about Mattucci's background and priorities at the [official bio page](https://www.torranceca.gov/government/city-council-and-elected-officials/mattucci).",
        "role": "Councilmember",
        "notes": [
            "Participated in 0 recorded votes",
            "Voted Yes on 0 motions",
            "Voted No on 0 motions",
            "Active in 0 policy areas"
        ],
        "stats": {
            "total_votes": 0,
            "yes_votes": 0,
            "no_votes": 0
        },
        "bio_url": "https://www.torranceca.gov/government/city-council-and-elected-officials/mattucci",
        "policy_focus": [
            "Planning & Development",
            "Public Safety",
            "Budget & Finance"
        ],
        "notable_initiatives": [
            "Development oversight",
            "Public safety initiatives",
            "Budget management"
        ],
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
    print("✅ Added AURELIO MATTUCCI summary")

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("\n✅ Aurelio Mattucci added back!")
    print(f"📊 Councilmembers: {data['councilmembers']}")
    print(f"📝 Summaries available for: {list(data['councilmember_summaries'].keys())}")

if __name__ == "__main__":
    add_mattucci_back()
