#!/usr/bin/env python3
"""
Add meeting and councilmember summaries to the data file
"""

import json

def add_summaries():
    # Load the existing data
    with open('data/torrance_votes_consolidated_final.json', 'r') as f:
        data = json.load(f)

    print('📝 Adding meeting summaries to data...')

    # Meeting summaries with unique highlights
    meeting_summaries = {
        '14490': {
            'date': '2025-08-05',
            'title': 'City Council Meeting',
            'summary': 'Standard procedural meeting with 20 unanimous votes. Featured one public hearing on land use study regarding accessory dwelling units and junior accessory dwelling units.',
            'unique_aspects': [
                'Public hearing on land use study for accessory dwelling units',
                'All 20 votes passed unanimously',
                'Standard procedural meeting'
            ],
            'key_items': [
                'Land Use Study 25-00001 - Accessory Dwelling Units regulation',
                'Consent Calendar items'
            ]
        },
        '14510': {
            'date': '2025-08-19',
            'title': 'City Council Meeting',
            'summary': 'Most contentious meeting with 5 failed votes out of 24 total. Featured Police Chief Jeremiah Hart retirement resolution, Youth Council appointments, and significant planning/development public hearings.',
            'unique_aspects': [
                '5 failed votes (unusual - most meetings have 100% pass rate)',
                'Police Chief Jeremiah Hart retirement resolution',
                'Youth Council appointments',
                '2 public hearings on planning/development',
                'Financial decisions including $200,000 expenditure'
            ],
            'key_items': [
                'Police Chief Jeremiah Hart retirement resolution',
                '2025-2026 Torrance Youth Council appointments',
                'Columbia Park Community Engagement project',
                'Planning Commission appeals and modifications',
                'Encampment Prevention Security Guard Services ($200,000)'
            ]
        },
        '14524': {
            'date': '2025-09-16',
            'title': 'City Council Meeting',
            'summary': 'Minimal activity meeting with only 4 votes, all procedural items.',
            'unique_aspects': [
                'Lowest activity meeting (4 votes)',
                'All procedural items',
                'All votes passed unanimously'
            ],
            'key_items': [
                'Standard procedural items only'
            ]
        },
        '14530': {
            'date': '2025-09-23',
            'title': 'City Council Meeting',
            'summary': 'Most active meeting with 31 votes, all passed. Featured Police Officer Claude Fierro retirement resolution, commission appointments, coyote management plan, and economic development initiatives.',
            'unique_aspects': [
                'Highest activity meeting (31 votes)',
                'Police Officer Claude Fierro retirement resolution',
                'Multiple commission appointments',
                'Coyote management plan discussion',
                'Economic development initiatives',
                'All votes passed unanimously'
            ],
            'key_items': [
                'Police Officer Claude Fierro retirement resolution',
                'Commission appointments (Aging, Environmental, Historic Preservation)',
                'Coyote Management Plan Update',
                'Economic Development Update',
                'Public Access Defibrillator Program update',
                'Fire Code amendments public hearing'
            ]
        },
        '14536': {
            'date': '2025-10-07',
            'title': 'City Council Meeting',
            'summary': 'Significant decisions meeting with 3 failed votes out of 18 total. Featured Denise Thurston retirement resolution, Breast Cancer Awareness Month proclamation, Columbia Park renaming discussion, and WWII memorial event subsidy.',
            'unique_aspects': [
                '3 failed votes (indicates significant disagreement)',
                'Denise Thurston retirement resolution',
                'Breast Cancer Awareness Month proclamation',
                'Columbia Park renaming discussion',
                'WWII memorial event subsidy ($1,200)'
            ],
            'key_items': [
                'Denise Thurston retirement resolution',
                'Breast Cancer Awareness Month proclamation',
                'Columbia Park renaming discussion',
                'WWII Camp Memorial Fundraising Event subsidy',
                'Certificate of Participation Bond Funds'
            ]
        },
        '14538': {
            'date': '2025-10-14',
            'title': 'City Council Meeting',
            'summary': 'Standard procedural meeting with 10 votes, all passed unanimously.',
            'unique_aspects': [
                'Standard procedural meeting',
                'All 10 votes passed unanimously',
                'Minimal unique agenda items'
            ],
            'key_items': [
                'Standard procedural items only'
            ]
        }
    }

    # Councilmember summaries
    councilmember_summaries = {
        'Chen': {
            'role': 'Mayor',
            'full_name': 'George Chen',
            'summary': 'Mayor of Torrance. Limited individual voting data available in current dataset, but serves as the presiding officer of the City Council.',
            'notes': [
                'Serves as Mayor and presiding officer',
                'Limited individual vote records in current data',
                'Most votes show only tally results, not individual positions'
            ]
        },
        'Gerson': {
            'role': 'Councilmember',
            'full_name': 'Councilmember Gerson',
            'summary': 'City Councilmember. Limited individual voting data available in current dataset. Most votes show only tally results rather than individual positions.',
            'notes': [
                'City Councilmember',
                'Limited individual vote records in current data',
                'Most votes show only tally results, not individual positions'
            ]
        },
        'Kaji': {
            'role': 'Councilmember',
            'full_name': 'Councilmember Kaji',
            'summary': 'City Councilmember. Limited individual voting data available in current dataset. Most votes show only tally results rather than individual positions.',
            'notes': [
                'City Councilmember',
                'Limited individual vote records in current data',
                'Most votes show only tally results, not individual positions'
            ]
        },
        'Kalani': {
            'role': 'Councilmember',
            'full_name': 'Councilmember Kalani',
            'summary': 'City Councilmember. Limited individual voting data available in current dataset. Most votes show only tally results rather than individual positions.',
            'notes': [
                'City Councilmember',
                'Limited individual vote records in current data',
                'Most votes show only tally results, not individual positions'
            ]
        },
        'Lewis': {
            'role': 'Councilmember',
            'full_name': 'Councilmember Lewis',
            'summary': 'City Councilmember. Limited individual voting data available in current dataset. Most votes show only tally results rather than individual positions.',
            'notes': [
                'City Councilmember',
                'Limited individual vote records in current data',
                'Most votes show only tally results, not individual positions'
            ]
        },
        'Mattucci': {
            'role': 'Councilmember',
            'full_name': 'Councilmember Mattucci',
            'summary': 'City Councilmember. Limited individual voting data available in current dataset. Most votes show only tally results rather than individual positions.',
            'notes': [
                'City Councilmember',
                'Limited individual vote records in current data',
                'Most votes show only tally results, not individual positions'
            ]
        },
        'Sheikh': {
            'role': 'Councilmember',
            'full_name': 'Councilmember Sheikh',
            'summary': 'City Councilmember. Limited individual voting data available in current dataset. Most votes show only tally results rather than individual positions.',
            'notes': [
                'City Councilmember',
                'Limited individual vote records in current data',
                'Most votes show only tally results, not individual positions'
            ]
        }
    }

    # Add summaries to the data structure
    data['meeting_summaries'] = meeting_summaries
    data['councilmember_summaries'] = councilmember_summaries

    # Update metadata
    data['metadata']['has_meeting_summaries'] = True
    data['metadata']['has_councilmember_summaries'] = True
    data['metadata']['summaries_created_at'] = '2025-10-20T15:45:00'

    print('✅ Meeting summaries added')
    print('✅ Councilmember summaries added')
    print('✅ Metadata updated')

    # Save the updated data
    with open('data/torrance_votes_consolidated_final.json', 'w') as f:
        json.dump(data, f, indent=2)

    print('💾 Data file updated successfully!')
    print()
    print('📊 Summary:')
    print(f'• {len(meeting_summaries)} meeting summaries added')
    print(f'• {len(councilmember_summaries)} councilmember summaries added')
    print('• Summaries now available for display throughout the application')

if __name__ == '__main__':
    add_summaries()
