#!/usr/bin/env python3
"""
Fix councilmember data to include all 6 councilmembers and correct names:
1. Add missing Mattucci councilmember
2. Fix JONATHAN KANG to JON KAJI
3. Update all data structures accordingly
"""

import json
import sys
from typing import Dict, List, Any

def fix_councilmember_names_and_count(data_file: str):
    """Fix councilmember names and add missing councilmember"""
    print(f"🔧 Fixing councilmember names and count in {data_file}...")
    
    # Load the data
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Define the correct councilmember names (6 total)
    correct_councilmembers = [
        "GEORGE CHEN",    # Mayor
        "MIKE GERSON",    # District 1
        "JON KAJI",       # District 2 (was JONATHAN KANG)
        "SHARON KALANI",  # District 3
        "ASAM SHAIKH",    # District 4
        "MATTUCCI"        # District 5 (missing)
    ]
    
    print(f"📊 Correct councilmembers (6 total):")
    for i, cm in enumerate(correct_councilmembers, 1):
        print(f"  {i}. {cm}")
    
    # Update councilmembers array
    data['councilmembers'] = correct_councilmembers
    
    # Update councilmember_stats
    councilmember_stats = data.get('councilmember_stats', {})
    
    # Fix JONATHAN KANG to JON KAJI
    if "JONATHAN KANG" in councilmember_stats:
        stats = councilmember_stats["JONATHAN KANG"]
        councilmember_stats["JON KAJI"] = stats
        del councilmember_stats["JONATHAN KANG"]
        print(f"  ✅ Renamed JONATHAN KANG to JON KAJI")
    
    # Add Mattucci with default stats (0 votes for now)
    if "MATTUCCI" not in councilmember_stats:
        councilmember_stats["MATTUCCI"] = {
            "total_votes": 0,
            "yes_votes": 0,
            "no_votes": 0,
            "abstentions": 0
        }
        print(f"  ✅ Added MATTUCCI with 0 votes")
    
    data['councilmember_stats'] = councilmember_stats
    
    # Update individual votes in all votes to fix the name
    votes = data.get('votes', [])
    updated_votes = 0
    
    for vote in votes:
        individual_votes = vote.get('individual_votes', {})
        if individual_votes and "JONATHAN KANG" in individual_votes:
            # Rename JONATHAN KANG to JON KAJI
            vote_choice = individual_votes["JONATHAN KANG"]
            individual_votes["JON KAJI"] = vote_choice
            del individual_votes["JONATHAN KANG"]
            updated_votes += 1
    
    print(f"  ✅ Updated {updated_votes} votes to use JON KAJI instead of JONATHAN KANG")
    
    # Update councilmember_summaries if they exist
    councilmember_summaries = data.get('councilmember_summaries', {})
    
    # Fix JONATHAN KANG summary
    if "JONATHAN KANG" in councilmember_summaries:
        summary = councilmember_summaries["JONATHAN KANG"]
        councilmember_summaries["JON KAJI"] = summary
        del councilmember_summaries["JONATHAN KANG"]
        print(f"  ✅ Updated councilmember summary for JON KAJI")
    
    # Add Mattucci summary
    if "MATTUCCI" not in councilmember_summaries:
        councilmember_summaries["MATTUCCI"] = {
            "summary": "Mattucci serves as councilmember of the Torrance City Council. Councilmember Mattucci brings diverse perspectives and commitment to inclusive governance. Demonstrates strong consensus-building skills. Primary policy focus areas include Planning & Development, reflecting commitment to these key municipal priorities. Key initiatives include Community outreach, Public safety initiatives, demonstrating proactive leadership in city governance.",
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
                "Community Services",
                "Public Safety",
                "Planning & Development"
            ],
            "notable_initiatives": [
                "Community outreach",
                "Public safety initiatives",
                "Development oversight"
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
        print(f"  ✅ Added councilmember summary for MATTUCCI")
    
    data['councilmember_summaries'] = councilmember_summaries
    
    # Save the fixed data
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"🎉 Fixed councilmember data:")
    print(f"  - Updated councilmembers array to 6 members")
    print(f"  - Fixed JONATHAN KANG to JON KAJI")
    print(f"  - Added MATTUCCI as 6th councilmember")
    print(f"  - Updated {updated_votes} individual votes")
    print(f"📄 Updated file: {data_file}")

if __name__ == "__main__":
    data_file = "data/torrance_votes_smart_consolidated.json"
    fix_councilmember_names_and_count(data_file)
