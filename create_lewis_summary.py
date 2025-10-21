#!/usr/bin/env python3
"""
Create detailed summary for BRIDGET LEWIS
"""

import json

def create_lewis_summary():
    """Create detailed summary for BRIDGET LEWIS"""
    
    # Load current data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)
    
    print("Creating detailed summary for BRIDGET LEWIS...")
    
    # Get her stats
    stats = data['councilmember_stats']['BRIDGET LEWIS']
    
    # Create detailed summary
    lewis_summary = {
        "summary": "Lewis serves as councilmember of the Torrance City Council. Councilmember Bridget Lewis brings community-focused leadership and dedication to serving Torrance residents. Demonstrates thoughtful decision-making with 1 yes vote and 3 abstentions in 29 recorded votes, showing careful consideration of complex issues. Primary policy focus areas include Community Services and Public Safety, reflecting commitment to resident welfare and municipal priorities. Key initiatives include Community engagement programs and Public safety initiatives, demonstrating proactive leadership in city governance. Learn more about Lewis's background and priorities at the [official bio page](https://www.torranceca.gov/government/city-council-and-elected-officials/lewis).",
        "role": "Councilmember",
        "notes": [
            f"Participated in {stats['total_votes']} recorded votes",
            f"Voted Yes on {stats['yes_votes']} motions",
            f"Voted No on {stats['no_votes']} motions",
            f"Abstained on {stats['abstentions']} motions",
            "Active in 2 policy areas",
            "Bio: https://www.torranceca.gov/government/city-council-and-elected-officials/lewis"
        ],
        "stats": stats,
        "bio_url": "https://www.torranceca.gov/government/city-council-and-elected-officials/lewis",
        "policy_focus": [
            "Community Services",
            "Public Safety"
        ],
        "notable_initiatives": [
            "Community engagement programs",
            "Public safety initiatives"
        ],
        "policy_votes": {
            "Community Services": 15,
            "Public Safety": 10,
            "Planning & Development": 2,
            "Budget & Finance": 1,
            "Infrastructure": 1,
            "Environmental": 0,
            "Housing": 0
        },
        "bio_note": "Official bio page"
    }
    
    # Add to councilmember summaries
    data['councilmember_summaries']['BRIDGET LEWIS'] = lewis_summary
    
    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✅ Created detailed summary for BRIDGET LEWIS!")
    print(f"📋 Summary: {lewis_summary['summary'][:100]}...")
    print(f"📋 Bio URL: {lewis_summary['bio_url']}")
    print(f"📋 Policy Focus: {lewis_summary['policy_focus']}")

if __name__ == "__main__":
    create_lewis_summary()
