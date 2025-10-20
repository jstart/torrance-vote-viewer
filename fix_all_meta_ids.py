#!/usr/bin/env python3
"""
Comprehensive Meta ID Fixer for Torrance Vote Viewer

This script fixes meta_id and timestamp issues across all meetings by:
1. Loading meta_id mappings and video timestamps
2. Intelligently matching agenda items to meta_ids
3. Updating consolidated data with correct meta_ids and timestamps
4. Providing detailed reporting of fixes applied

Usage: python3 fix_all_meta_ids.py
"""

import json
import re
from typing import Dict, List, Tuple, Optional

def load_data():
    """Load all required data files"""
    print("📂 Loading data files...")
    
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        consolidated_data = json.load(f)
    
    with open('data/meta_id_mapping.json', 'r') as f:
        meta_mapping = json.load(f)
    
    with open('data/video_timestamps.json', 'r') as f:
        timestamp_data = json.load(f)
    
    return consolidated_data, meta_mapping, timestamp_data

def normalize_text(text: str) -> str:
    """Normalize text for better matching"""
    if not text:
        return ""
    
    # Convert to uppercase and remove extra whitespace
    normalized = re.sub(r'\s+', ' ', text.upper().strip())
    
    # Remove common punctuation and special characters
    normalized = re.sub(r'[^\w\s]', '', normalized)
    
    # Remove common words that might interfere with matching
    stop_words = ['THE', 'A', 'AN', 'AND', 'OR', 'BUT', 'IN', 'ON', 'AT', 'TO', 'FOR', 'OF', 'WITH', 'BY']
    words = normalized.split()
    words = [word for word in words if word not in stop_words]
    
    return ' '.join(words)

def extract_key_phrases(agenda_item: str) -> List[str]:
    """Extract key phrases from agenda item for matching"""
    phrases = []
    
    # Extract item number (e.g., "9A", "12", "14")
    item_match = re.search(r'^(\d+[A-Z]?)\s*\.', agenda_item)
    if item_match:
        phrases.append(item_match.group(1))
    
    # Extract key words from title
    title_part = re.sub(r'^\d+[A-Z]?\s*\.\s*', '', agenda_item)
    
    # Look for specific patterns
    patterns = [
        r'PLANNING COMMISSION',
        r'COMMUNITY DEVELOPMENT',
        r'ORAL COMMUNICATIONS',
        r'ADJOURNMENT',
        r'CONSENT CALENDAR',
        r'HEARINGS',
        r'COUNCIL COMMITTEE',
        r'COMMUNITY SERVICES',
        r'RESOLUTION',
        r'ORDINANCE',
        r'PUBLIC HEARING',
        r'ACCEPT AND FILE'
    ]
    
    for pattern in patterns:
        if re.search(pattern, title_part, re.IGNORECASE):
            phrases.append(pattern)
    
    return phrases

def find_best_meta_id_match(agenda_item: str, available_meta_ids: Dict[str, int]) -> Optional[int]:
    """Find the best meta_id match for an agenda item"""
    if not available_meta_ids:
        return None
    
    agenda_normalized = normalize_text(agenda_item)
    agenda_phrases = extract_key_phrases(agenda_item)
    
    best_match = None
    best_score = 0
    
    for meta_key, meta_id in available_meta_ids.items():
        meta_normalized = normalize_text(meta_key)
        
        # Calculate match score
        score = 0
        
        # Exact phrase matches get highest score
        for phrase in agenda_phrases:
            if phrase in meta_normalized:
                score += 10
        
        # Word overlap score
        agenda_words = set(agenda_normalized.split())
        meta_words = set(meta_normalized.split())
        word_overlap = len(agenda_words.intersection(meta_words))
        score += word_overlap * 2
        
        # Length similarity bonus
        length_diff = abs(len(agenda_normalized) - len(meta_normalized))
        if length_diff < 50:  # Similar length
            score += 1
        
        if score > best_score:
            best_score = score
            best_match = meta_id
    
    # Only return match if score is high enough
    return best_match if best_score >= 5 else None

def fix_meeting_meta_ids(meeting_id: str, votes: List[Dict], meta_mapping: Dict, timestamp_data: Dict) -> List[Dict]:
    """Fix meta_ids for all votes in a meeting"""
    fixes_applied = []
    
    if meeting_id not in meta_mapping:
        print(f"  ❌ No meta_id mapping available for meeting {meeting_id}")
        return fixes_applied
    
    available_meta_ids = meta_mapping[meeting_id]
    meeting_timestamps = timestamp_data.get('meeting_meta_timestamps', {}).get(meeting_id, {})
    
    for vote in votes:
        agenda_item = vote.get('agenda_item', '')
        current_meta_id = vote.get('meta_id')
        current_timestamp = vote.get('video_timestamp')
        
        # Skip if already has meta_id and timestamp
        if current_meta_id and current_timestamp and not vote.get('timestamp_estimated'):
            continue
        
        # Try to find better match
        best_meta_id = find_best_meta_id_match(agenda_item, available_meta_ids)
        
        if best_meta_id and str(best_meta_id) in meeting_timestamps:
            new_timestamp = meeting_timestamps[str(best_meta_id)]
            
            # Apply fix
            vote['meta_id'] = best_meta_id
            vote['video_timestamp'] = new_timestamp
            vote['timestamp_estimated'] = False
            
            fixes_applied.append({
                'agenda_item': agenda_item[:50] + '...',
                'old_meta_id': current_meta_id,
                'new_meta_id': best_meta_id,
                'old_timestamp': current_timestamp,
                'new_timestamp': new_timestamp
            })
    
    return fixes_applied

def main():
    """Main function to fix all meta_id issues"""
    print("🔧 Comprehensive Meta ID Fixer")
    print("=" * 50)
    
    # Load data
    consolidated_data, meta_mapping, timestamp_data = load_data()
    
    votes = consolidated_data.get('votes', [])
    meetings = consolidated_data.get('meetings', {})
    
    total_fixes = 0
    
    print(f"\n📊 Processing {len(meetings)} meetings...")
    print()
    
    for meeting_id in sorted(meetings.keys()):
        meeting_votes = [v for v in votes if v.get('meeting_id') == meeting_id]
        
        print(f"📋 Meeting {meeting_id}:")
        print(f"  Processing {len(meeting_votes)} votes...")
        
        fixes = fix_meeting_meta_ids(meeting_id, meeting_votes, meta_mapping, timestamp_data)
        
        if fixes:
            print(f"  ✅ Applied {len(fixes)} fixes:")
            for fix in fixes:
                print(f"    - {fix['agenda_item']}")
                print(f"      meta_id: {fix['old_meta_id']} → {fix['new_meta_id']}")
                print(f"      timestamp: {fix['old_timestamp']} → {fix['new_timestamp']}")
            total_fixes += len(fixes)
        else:
            print(f"  ✅ No fixes needed")
        
        print()
    
    # Save updated data
    print(f"💾 Saving updated data...")
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(consolidated_data, f, indent=2)
    
    print(f"\n🎉 Summary:")
    print(f"  Total fixes applied: {total_fixes}")
    print(f"  Meetings processed: {len(meetings)}")
    print(f"  ✅ Data saved successfully!")
    
    # Final verification
    print(f"\n🔍 Final verification:")
    votes_with_meta = len([v for v in votes if v.get('meta_id')])
    votes_without_meta = len([v for v in votes if not v.get('meta_id')])
    estimated_votes = len([v for v in votes if v.get('timestamp_estimated')])
    
    print(f"  Votes with meta_id: {votes_with_meta}")
    print(f"  Votes without meta_id: {votes_without_meta}")
    print(f"  Votes with estimated timestamps: {estimated_votes}")

if __name__ == '__main__':
    main()
