#!/usr/bin/env python3
"""
Fix Mattucci's vote data by reprocessing frame images with Gemini
"""

import json
import os
import base64
import requests
from pathlib import Path

def encode_image(image_path):
    """Encode image to base64 for Gemini API"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_vote_frame_with_gemini(image_path, api_key):
    """Use Gemini to analyze vote frame and extract individual votes"""

    # Encode the image
    base64_image = encode_image(image_path)

    # Gemini API request
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [{
                "text": """Analyze this city council voting results screen and extract the individual votes for each councilmember.

Look for:
- Councilmember names (Gerson, Kaji, Kalani, Lewis, Mattucci, Sheikh, Chen)
- Their vote choices (Y for Yes, N for No, A for Abstain, R for Recuse)

Return ONLY a JSON object with this exact format:
{
  "GEORGE CHEN": "YES/NO/ABSTAIN",
  "MIKE GERSON": "YES/NO/ABSTAIN",
  "SHARON KALANI": "YES/NO/ABSTAIN",
  "JON KAJI": "YES/NO/ABSTAIN",
  "ASAM SHEIKH": "YES/NO/ABSTAIN",
  "AURELIO MATTUCCI": "YES/NO/ABSTAIN",
  "BRIDGET LEWIS": "YES/NO/ABSTAIN"
}

Be very careful to identify Mattucci's vote correctly. Look for "Councilmember Mattucci" or "Mattucci" in the list.""",
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64_image
                }
            }]
        }]
    }

    headers = {
        'Content-Type': 'application/json',
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        result = response.json()
        content = result['candidates'][0]['content']['parts'][0]['text']

        # Extract JSON from the response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            vote_data = json.loads(json_match.group())
            return vote_data
        else:
            print(f"Could not extract JSON from response: {content}")
            return None

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return None

def fix_mattucci_votes():
    """Fix Mattucci's vote data by reprocessing frames"""

    # Load vote data
    with open('data/torrance_votes_smart_consolidated.json', 'r') as f:
        data = json.load(f)

    # Get Gemini API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY environment variable not set")
        return

    print("🔍 Analyzing Mattucci's votes...")

    # Find votes where Mattucci is marked as ABSTAIN
    mattucci_abstain_votes = []
    for vote in data.get('votes', []):
        if (vote.get('individual_votes', {}).get('AURELIO MATTUCCI') == 'ABSTAIN'
            and vote.get('frame_available')
            and vote.get('frame_path')):
            mattucci_abstain_votes.append(vote)

    print(f"Found {len(mattucci_abstain_votes)} votes where Mattucci is marked as ABSTAIN with available frames")

    fixed_count = 0
    error_count = 0

    for i, vote in enumerate(mattucci_abstain_votes[:10]):  # Process first 10 for testing
        print(f"\n📊 Processing vote {i+1}/{min(10, len(mattucci_abstain_votes))}")
        print(f"   Meeting: {vote.get('meeting_id')}")
        print(f"   Agenda: {vote.get('agenda_item', '')[:50]}...")
        print(f"   Frame: {vote.get('frame_number')}")

        frame_path = vote.get('frame_path')
        if os.path.exists(frame_path):
            print(f"   ✅ Frame exists: {frame_path}")

            # Analyze with Gemini
            gemini_result = analyze_vote_frame_with_gemini(frame_path, api_key)

            if gemini_result and 'AURELIO MATTUCCI' in gemini_result:
                mattucci_vote = gemini_result['AURELIO MATTUCCI']
                print(f"   🎯 Gemini says Mattucci voted: {mattucci_vote}")

                # Update the vote data
                vote['individual_votes']['AURELIO MATTUCCI'] = mattucci_vote
                fixed_count += 1

                # Also update the vote tally if needed
                if mattucci_vote == 'YES':
                    vote['vote_tally']['ayes'] = vote['vote_tally'].get('ayes', 0) + 1
                    vote['vote_tally']['abstentions'] = max(0, vote['vote_tally'].get('abstentions', 0) - 1)
                elif mattucci_vote == 'NO':
                    vote['vote_tally']['noes'] = vote['vote_tally'].get('noes', 0) + 1
                    vote['vote_tally']['abstentions'] = max(0, vote['vote_tally'].get('abstentions', 0) - 1)

                print(f"   ✅ Updated vote data")
            else:
                print(f"   ❌ Could not extract Mattucci's vote from Gemini response")
                error_count += 1
        else:
            print(f"   ❌ Frame not found: {frame_path}")
            error_count += 1

    # Save updated data
    with open('data/torrance_votes_smart_consolidated.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n📊 Fix Results:")
    print(f"   - Fixed: {fixed_count} votes")
    print(f"   - Errors: {error_count} votes")
    print(f"   - Total processed: {min(10, len(mattucci_abstain_votes))} votes")

    # Show updated stats
    mattucci_yes = sum(1 for vote in data.get('votes', [])
                      if vote.get('individual_votes', {}).get('AURELIO MATTUCCI') == 'YES')
    mattucci_abstain = sum(1 for vote in data.get('votes', [])
                          if vote.get('individual_votes', {}).get('AURELIO MATTUCCI') == 'ABSTAIN')

    print(f"\n📈 Updated Mattucci Stats:")
    print(f"   - YES votes: {mattucci_yes}")
    print(f"   - ABSTAIN votes: {mattucci_abstain}")

if __name__ == "__main__":
    fix_mattucci_votes()
