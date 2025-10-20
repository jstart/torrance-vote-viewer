#!/usr/bin/env python3
"""
Email Subscription Manager for Torrance Vote Viewer

This script manages email subscriptions and can be used to notify subscribers
when new meeting data is added to the system.

Usage:
    python3 email_manager.py --action subscribe --email user@example.com
    python3 email_manager.py --action notify --message "New meetings added"
    python3 email_manager.py --action list
"""

import json
import argparse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

class EmailSubscriptionManager:
    def __init__(self, subscriptions_file='data/email_subscriptions.json'):
        self.subscriptions_file = subscriptions_file
        self.subscriptions = self.load_subscriptions()
    
    def load_subscriptions(self):
        """Load subscriptions from file"""
        try:
            if os.path.exists(self.subscriptions_file):
                with open(self.subscriptions_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"Error loading subscriptions: {e}")
            return []
    
    def save_subscriptions(self):
        """Save subscriptions to file"""
        try:
            os.makedirs(os.path.dirname(self.subscriptions_file), exist_ok=True)
            with open(self.subscriptions_file, 'w') as f:
                json.dump(self.subscriptions, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving subscriptions: {e}")
            return False
    
    def subscribe(self, email):
        """Add email to subscription list"""
        if email in self.subscriptions:
            return False, "Email already subscribed"
        
        self.subscriptions.append(email)
        if self.save_subscriptions():
            return True, "Successfully subscribed"
        else:
            return False, "Failed to save subscription"
    
    def unsubscribe(self, email):
        """Remove email from subscription list"""
        if email not in self.subscriptions:
            return False, "Email not found in subscriptions"
        
        self.subscriptions.remove(email)
        if self.save_subscriptions():
            return True, "Successfully unsubscribed"
        else:
            return False, "Failed to save changes"
    
    def list_subscriptions(self):
        """List all subscribed emails"""
        return self.subscriptions
    
    def send_notification(self, subject, message, smtp_config=None):
        """Send notification to all subscribers"""
        if not self.subscriptions:
            return False, "No subscribers to notify"
        
        if not smtp_config:
            # For demo purposes, just log the notification
            print(f"NOTIFICATION TO {len(self.subscriptions)} SUBSCRIBERS:")
            print(f"Subject: {subject}")
            print(f"Message: {message}")
            print(f"Recipients: {', '.join(self.subscriptions)}")
            return True, f"Notification logged for {len(self.subscriptions)} subscribers"
        
        # In a real implementation, you would send actual emails here
        try:
            # This is where you'd implement actual email sending
            # using smtplib or a service like SendGrid, Mailgun, etc.
            pass
        except Exception as e:
            return False, f"Failed to send emails: {e}"
    
    def notify_new_meetings(self, meeting_count, meeting_dates):
        """Send notification about new meetings"""
        subject = f"New Torrance City Council Meetings Available ({meeting_count})"
        
        message = f"""
Dear Subscriber,

{meeting_count} new City Council meeting(s) have been added to the Torrance Vote Viewer:

{chr(10).join(f"- {date}" for date in meeting_dates)}

You can view the latest meetings and votes at:
https://truman4congress.com/torrance-vote-viewer/

Thank you for staying informed about your local government!

Best regards,
Torrance Vote Viewer Team

---
To unsubscribe, reply to this email with "UNSUBSCRIBE" in the subject line.
        """.strip()
        
        return self.send_notification(subject, message)

def main():
    parser = argparse.ArgumentParser(description='Manage email subscriptions for Torrance Vote Viewer')
    parser.add_argument('--action', choices=['subscribe', 'unsubscribe', 'list', 'notify'], 
                       required=True, help='Action to perform')
    parser.add_argument('--email', help='Email address for subscribe/unsubscribe')
    parser.add_argument('--message', help='Message for notification')
    parser.add_argument('--subject', help='Subject for notification')
    
    args = parser.parse_args()
    
    manager = EmailSubscriptionManager()
    
    if args.action == 'subscribe':
        if not args.email:
            print("Error: --email required for subscribe action")
            return
        
        success, message = manager.subscribe(args.email)
        print(f"{'Success' if success else 'Error'}: {message}")
    
    elif args.action == 'unsubscribe':
        if not args.email:
            print("Error: --email required for unsubscribe action")
            return
        
        success, message = manager.unsubscribe(args.email)
        print(f"{'Success' if success else 'Error'}: {message}")
    
    elif args.action == 'list':
        subscriptions = manager.list_subscriptions()
        print(f"Total subscribers: {len(subscriptions)}")
        for email in subscriptions:
            print(f"  - {email}")
    
    elif args.action == 'notify':
        subject = args.subject or "Torrance Vote Viewer Update"
        message = args.message or "New meeting data is available"
        
        success, result_message = manager.send_notification(subject, message)
        print(f"{'Success' if success else 'Error'}: {result_message}")

if __name__ == '__main__':
    main()
