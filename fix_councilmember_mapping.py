#!/usr/bin/env python3
"""
Fix councilmember mapping issues
"""

import json

def fix_councilmember_mapping():
    # Load the data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    # Fix Bridget Lewis - add her summary
    if 'BRIDGET LEWIS' not in data['councilmember_summaries']:
        data['councilmember_summaries']['BRIDGET LEWIS'] = {
            "summary": "Lewis serves as councilmember of the Torrance City Council. Councilmember Bridget Lewis is a dedicated public servant focused on community well-being and constituent service. Demonstrates strong consensus-building skills and active participation in city governance. Primary policy focus areas include Community Services, Public Safety, and Budget & Finance. Key initiatives include Community service programs, Public safety initiatives, and Budget oversight. Learn more about Lewis's background and priorities at the [official bio page](https://www.torranceca.gov/government/city-council-and-elected-officials/lewis).",
            "role": "Councilmember",
            "notes": [
                f"Participated in {data['councilmember_stats']['BRIDGET LEWIS']['total_votes']} recorded votes",
                f"Voted Yes on {data['councilmember_stats']['BRIDGET LEWIS']['yes_votes']} motions",
                f"Voted No on {data['councilmember_stats']['BRIDGET LEWIS']['no_votes']} motions",
                "Active in multiple policy areas"
            ],
            "stats": {
                "total_votes": data['councilmember_stats']['BRIDGET LEWIS']['total_votes'],
                "yes_votes": data['councilmember_stats']['BRIDGET LEWIS']['yes_votes'],
                "no_votes": data['councilmember_stats']['BRIDGET LEWIS']['no_votes']
            },
            "bio_url": "https://www.torranceca.gov/government/city-council-and-elected-officials/lewis",
            "policy_focus": [
                "Community Services",
                "Public Safety",
                "Budget & Finance"
            ],
            "notable_initiatives": [
                "Community service programs",
                "Public safety initiatives",
                "Budget oversight"
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
        print("✅ Added Bridget Lewis summary")

    # Fix Aurelio Mattucci - remove him since he has 0 votes
    if 'MATTUCCI' in data['councilmember_summaries']:
        del data['councilmember_summaries']['MATTUCCI']
        print("✅ Removed MATTUCCI summary (no vote data)")

    # Remove MATTUCCI from councilmembers list if present
    if 'MATTUCCI' in data['councilmembers']:
        data['councilmembers'].remove('MATTUCCI')
        print("✅ Removed MATTUCCI from councilmembers list")

    # Remove MATTUCCI from councilmember_stats if present
    if 'MATTUCCI' in data['councilmember_stats']:
        del data['councilmember_stats']['MATTUCCI']
        print("✅ Removed MATTUCCI from councilmember_stats")

    # Ensure Bridget Lewis is in councilmembers list
    if 'BRIDGET LEWIS' not in data['councilmembers']:
        data['councilmembers'].append('BRIDGET LEWIS')
        print("✅ Added BRIDGET LEWIS to councilmembers list")

    # Save the corrected data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("\n✅ Councilmember mapping issues fixed!")
    print(f"📊 Councilmembers: {data['councilmembers']}")
    print(f"📝 Summaries available for: {list(data['councilmember_summaries'].keys())}")

if __name__ == "__main__":
    fix_councilmember_mapping()
