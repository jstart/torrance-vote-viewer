// Utility functions for Torrance Vote Viewer

class VoteViewerUtils {
    // Convert markdown-style links to HTML links
    static convertMarkdownLinks(text) {
        return text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="link-style">$1</a>');
    }

    // Convert plain URLs to clickable links
    static convertUrlsToLinks(text) {
        return text.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" class="link-style">$1</a>');
    }

    // Export vote data to CSV format
    static exportToCSV(votes, filename = 'torrance_votes.csv') {
        const headers = [
            'Meeting ID',
            'Meeting Date',
            'Meeting Time',
            'Agenda Item',
            'Vote Result',
            'Ayes',
            'Noes',
            'Abstentions',
            'Recused',
            'Video Timestamp',
            'Video URL',
            'Agenda URL',
            'Meta ID',
            'Frame Number',
            'Timestamp Estimated'
        ];
        
        const csvContent = [
            headers.join(','),
            ...votes.map(vote => [
                vote.meeting_id || '',
                vote.date || '',
                vote.time || '',
                `"${(vote.agenda_item || '').replace(/"/g, '""')}"`,
                vote.result || '',
                vote.vote_tally?.ayes || 0,
                vote.vote_tally?.noes || 0,
                vote.vote_tally?.abstentions || 0,
                vote.vote_tally?.recused || 0,
                vote.video_timestamp || '',
                vote.video_url || '',
                vote.agenda_url || '',
                vote.meta_id || '',
                vote.frame_number || '',
                vote.timestamp_estimated ? 'Yes' : 'No'
            ].join(','))
        ].join('\n');
        
        this.downloadFile(csvContent, filename, 'text/csv');
    }
    
    // Export vote data to JSON format
    static exportToJSON(votes, filename = 'torrance_votes.json') {
        const exportData = {
            export_date: new Date().toISOString(),
            total_votes: votes.length,
            votes: votes.map(vote => ({
                meeting_id: vote.meeting_id,
                date: vote.date,
                time: vote.time,
                agenda_item: vote.agenda_item,
                result: vote.result,
                vote_tally: vote.vote_tally,
                individual_votes: vote.individual_votes,
                video_timestamp: vote.video_timestamp,
                video_url: vote.video_url,
                agenda_url: vote.agenda_url,
                meta_id: vote.meta_id,
                frame_number: vote.frame_number,
                timestamp_estimated: vote.timestamp_estimated
            }))
        };
        
        const jsonContent = JSON.stringify(exportData, null, 2);
        this.downloadFile(jsonContent, filename, 'application/json');
    }
    
    // Download file helper
    static downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }
    
    // Show notification
    static showNotification(message, type = 'info') {
        // Remove existing notifications
        const existingNotifications = document.querySelectorAll('.notification');
        existingNotifications.forEach(notification => notification.remove());
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

  // Format date and time in human-readable format with PST timezone
  static formatMeetingDateTime(dateStr, timeStr) {
    if (!dateStr) return 'Date not available';

    try {
      // Parse the date string (YYYY-MM-DD format)
      const date = new Date(dateStr + 'T00:00:00');

      // Format the date
      const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
      const month = monthNames[date.getMonth()];
      const day = date.getDate();
      const year = date.getFullYear();

      let formattedDate = `${month} ${day}, ${year}`;

      // Add time if available
      if (timeStr) {
        // Parse time string (HH:MM format)
        const [hours, minutes] = timeStr.split(':').map(Number);

        // Convert to 12-hour format
        let displayHours = hours;
        let ampm = 'AM';

        if (hours === 0) {
          displayHours = 12;
        } else if (hours === 12) {
          ampm = 'PM';
        } else if (hours > 12) {
          displayHours = hours - 12;
          ampm = 'PM';
        }

        formattedDate += ` at ${displayHours}:${minutes.toString().padStart(2, '0')} ${ampm} PST`;
      }

      return formattedDate;
    } catch (error) {
      console.error('Error formatting date:', error);
      return dateStr + (timeStr ? ` at ${timeStr}` : '');
    }
  }

    // Calculate vote statistics
    static calculateVoteStats(votes) {
        const passed = votes.filter(v => v.result && v.result.toLowerCase().includes('pass')).length;
        const failed = votes.filter(v => v.result && v.result.toLowerCase().includes('fail')).length;
        return { passed, failed };
    }

    // Generate video deep link
    static generateVideoDeepLink(vote) {
        const meetingId = vote.meeting_id;
        const metaId = vote.meta_id;

        if (!meetingId) return null;

        if (metaId) {
            return `https://torrance.granicus.com/player/clip/${meetingId}?view_id=8&meta_id=${metaId}&redirect=true`;
        } else {
            return `https://torrance.granicus.com/player/clip/${meetingId}`;
        }
    }

    // Generate agenda deep link
    static generateAgendaDeepLink(vote) {
        const meetingId = vote.meeting_id;
        if (!meetingId) return null;

        const viewIdMap = {
            '14510': '8',
            '14490': '8',
            '14538': '8',
            '14524': '8',
            '14530': '8',
            '14536': '8'
        };

        const viewId = viewIdMap[meetingId] || '8';
        return `https://torrance.granicus.com/GeneratedAgendaViewer.php?view_id=${viewId}&clip_id=${meetingId}`;
    }

    // Councilmember name mapping
    static getCouncilmemberNames() {
        return {
            'chen': 'Chen',
            'gerson': 'Gerson',
            'kaji': 'Kaji',
            'kalani': 'Kalani',
            'lewis': 'Lewis',
            'mattucci': 'Mattucci',
            'sheikh': 'Sheikh'
        };
    }

    // Get full name for councilmember
    static getFullName(councilmemberId) {
        const names = this.getCouncilmemberNames();
        return names[councilmemberId] || councilmemberId;
    }

    // Calculate timestamp for vote
    static calculateVoteTimestamp(vote) {
        let timestamp;
        let timestampSource;

        if (vote.video_timestamp !== undefined) {
            timestamp = this.formatTimestamp(vote.video_timestamp);
            timestampSource = vote.timestamp_estimated ? 'estimated' : 'actual';
        } else {
            const frameNumber = parseInt(vote.frame_number) || 0;
            const estimatedSeconds = Math.floor(frameNumber / 30);
            timestamp = this.formatTimestamp(estimatedSeconds);
            timestampSource = 'estimated';
        }

        return { timestamp, timestampSource };
    }
}
