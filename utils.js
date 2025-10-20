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

    // Format timestamp from seconds to MM:SS
    static formatTimestamp(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
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
