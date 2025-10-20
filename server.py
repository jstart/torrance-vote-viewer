#!/usr/bin/env python3
"""
Simple HTTP server for Torrance Vote Viewer static web app
Serves the static files and handles routing
"""

import http.server
import socketserver
import json
import os
import urllib.parse
from pathlib import Path

class TorranceVoteHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Parse the URL
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        # Handle API routes
        if path.startswith('/api/'):
            self.handle_api_request(path)
            return

        # Handle static file serving
        if path == '/' or path == '/index.html':
            self.serve_file('index.html')
        elif path.endswith('.json'):
            self.serve_file(path[1:])  # Remove leading slash
        elif path.endswith(('.js', '.css', '.html')):
            self.serve_file(path[1:])
        else:
            # For SPA routing, serve index.html for all non-file requests
            self.serve_file('index.html')

    def serve_file(self, filename):
        """Serve a static file"""
        try:
            with open(filename, 'rb') as f:
                content = f.read()

            # Set appropriate content type
            if filename.endswith('.json'):
                content_type = 'application/json'
            elif filename.endswith('.html'):
                content_type = 'text/html'
            elif filename.endswith('.js'):
                content_type = 'application/javascript'
            elif filename.endswith('.css'):
                content_type = 'text/css'
            else:
                content_type = 'text/plain'

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        except FileNotFoundError:
            self.send_error(404, f"File not found: {filename}")
        except Exception as e:
            self.send_error(500, f"Server error: {str(e)}")

    def handle_api_request(self, path):
        """Handle API requests (for future expansion)"""
        try:
            # Load the enhanced data
            with open('data/torrance_votes_enhanced.json', 'r') as f:
                data = json.load(f)

            if path == '/api/statistics':
                response = {
                    'success': True,
                    'data': data['metadata']
                }
            elif path == '/api/meetings':
                response = {
                    'success': True,
                    'data': list(data['meetings'].values())
                }
            elif path == '/api/councilmembers':
                response = {
                    'success': True,
                    'data': list(data['councilmembers'].values())
                }
            elif path == '/api/votes':
                response = {
                    'success': True,
                    'data': data['votes']
                }
            else:
                response = {
                    'success': False,
                    'error': 'API endpoint not found'
                }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            self.send_error(500, f"API error: {str(e)}")

    def log_message(self, format, *args):
        """Custom log format"""
        print(f"[{self.date_time_string()}] {format % args}")

def main():
    PORT = 8000

    # Change to the directory containing the files
    os.chdir(Path(__file__).parent)

    print(f"Starting Torrance Vote Viewer server on port {PORT}")
    print(f"Serving files from: {os.getcwd()}")
    print(f"Open your browser to: http://localhost:{PORT}")
    print("Press Ctrl+C to stop the server")

    with socketserver.TCPServer(("", PORT), TorranceVoteHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == "__main__":
    main()
