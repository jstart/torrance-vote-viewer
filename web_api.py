#!/usr/bin/env python3
"""
Torrance Vote Viewer - Web API
Simple Flask API for web viewer integration
"""

from flask import Flask, jsonify, request
from vote_query_system import TorranceVoteQuerySystem, VoteQuery
import json

app = Flask(__name__)

# Initialize the query system
query_system = TorranceVoteQuerySystem()

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Get overall vote statistics"""
    try:
        stats = query_system.get_statistics()
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/votes', methods=['GET'])
def get_votes():
    """Get votes with optional filters"""
    try:
        # Parse query parameters
        councilmember = request.args.get('councilmember')
        meeting_id = request.args.get('meeting_id')
        agenda_item = request.args.get('agenda_item')
        result = request.args.get('result')
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', 0, type=int)

        # Create query object
        query = VoteQuery(
            councilmember=councilmember,
            meeting_id=meeting_id,
            agenda_item=agenda_item,
            result=result,
            limit=limit,
            offset=offset
        )

        votes = query_system.get_all_votes(query)

        return jsonify({
            'success': True,
            'data': {
                'votes': votes,
                'count': len(votes),
                'filters': {
                    'councilmember': councilmember,
                    'meeting_id': meeting_id,
                    'agenda_item': agenda_item,
                    'result': result
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/councilmember/<name>', methods=['GET'])
def get_councilmember_record(name):
    """Get comprehensive voting record for a councilmember"""
    try:
        record = query_system.get_councilmember_voting_record(name)
        return jsonify({
            'success': True,
            'data': record
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/meeting/<meeting_id>', methods=['GET'])
def get_meeting_summary(meeting_id):
    """Get comprehensive summary for a meeting"""
    try:
        summary = query_system.get_meeting_summary(meeting_id)
        return jsonify({
            'success': True,
            'data': summary
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/search', methods=['GET'])
def search_votes():
    """Search votes by text"""
    try:
        search_term = request.args.get('q', '')
        fields = request.args.get('fields', 'agenda_item,motion_text').split(',')

        if not search_term:
            return jsonify({
                'success': False,
                'error': 'Search term (q) is required'
            }), 400

        results = query_system.search_votes(search_term, fields)

        return jsonify({
            'success': True,
            'data': {
                'votes': results,
                'count': len(results),
                'search_term': search_term,
                'fields': fields
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/councilmembers', methods=['GET'])
def get_councilmembers():
    """Get list of available councilmembers"""
    try:
        councilmembers = query_system.get_available_councilmembers()
        return jsonify({
            'success': True,
            'data': councilmembers
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/meetings', methods=['GET'])
def get_meetings():
    """Get list of available meetings"""
    try:
        meetings = query_system.get_available_meetings()
        return jsonify({
            'success': True,
            'data': meetings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/agenda-items', methods=['GET'])
def get_agenda_items():
    """Get list of available agenda items"""
    try:
        agenda_items = query_system.get_available_agenda_items()
        return jsonify({
            'success': True,
            'data': agenda_items
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/vote/<vote_id>', methods=['GET'])
def get_vote_details(vote_id):
    """Get detailed information for a specific vote"""
    try:
        # Find vote by ID
        votes = query_system.get_all_votes()
        vote = next((v for v in votes if v['id'] == vote_id), None)

        if not vote:
            return jsonify({
                'success': False,
                'error': f'Vote {vote_id} not found'
            }), 404

        return jsonify({
            'success': True,
            'data': vote
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        stats = query_system.get_statistics()
        return jsonify({
            'success': True,
            'status': 'healthy',
            'data': {
                'total_votes': stats['total_votes'],
                'total_meetings': stats['total_meetings'],
                'last_updated': query_system.data['metadata']['created_at']
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/', methods=['GET'])
def api_documentation():
    """API documentation endpoint"""
    return jsonify({
        'name': 'Torrance Vote Viewer API',
        'version': '1.0',
        'endpoints': {
            'GET /api/statistics': 'Get overall vote statistics',
            'GET /api/votes': 'Get votes with optional filters (?councilmember, ?meeting_id, ?agenda_item, ?result, ?limit, ?offset)',
            'GET /api/councilmember/<name>': 'Get voting record for a councilmember',
            'GET /api/meeting/<meeting_id>': 'Get meeting summary and votes',
            'GET /api/search': 'Search votes by text (?q=term&fields=agenda_item,motion_text)',
            'GET /api/councilmembers': 'Get list of available councilmembers',
            'GET /api/meetings': 'Get list of available meetings',
            'GET /api/agenda-items': 'Get list of available agenda items',
            'GET /api/vote/<vote_id>': 'Get detailed information for a specific vote',
            'GET /api/health': 'Health check endpoint'
        },
        'example_queries': {
            'all_votes': '/api/votes',
            'chen_votes': '/api/votes?councilmember=Chen',
            'meeting_votes': '/api/votes?meeting_id=14510',
            'passed_votes': '/api/votes?result=passed',
            'search_consent': '/api/search?q=consent',
            'chen_record': '/api/councilmember/Chen',
            'meeting_summary': '/api/meeting/14510'
        }
    })

if __name__ == '__main__':
    print("Starting Torrance Vote Viewer API...")
    print("API Documentation available at: http://localhost:5000/")
    print("Health check: http://localhost:5000/api/health")
    print("Statistics: http://localhost:5000/api/statistics")
    app.run(debug=True, host='0.0.0.0', port=5000)
