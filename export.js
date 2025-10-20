// Export and Sharing Features

class ExportManager {
    // Export vote data to CSV
    static exportToCSV(votes, filename = 'torrance_votes.csv') {
        const headers = [
            'Meeting ID',
            'Date',
            'Agenda Item',
            'Result',
            'Ayes',
            'Noes',
            'Abstentions',
            'Video Timestamp',
            'Video URL'
        ];

        const csvContent = [
            headers.join(','),
            ...votes.map(vote => [
                vote.meeting_id,
                vote.date,
                `"${vote.agenda_item.replace(/"/g, '""')}"`,
                vote.result,
                vote.vote_tally?.ayes || 0,
                vote.vote_tally?.noes || 0,
                vote.vote_tally?.abstentions || 0,
                vote.video_timestamp || '',
                vote.video_url || ''
            ].join(','))
        ].join('\n');

        this.downloadFile(csvContent, filename, 'text/csv');
    }

    // Export meeting summary to PDF
    static exportMeetingSummary(meeting, votes) {
        const summary = {
            title: `Meeting Summary - ${meeting.title}`,
            date: meeting.date,
            totalVotes: votes.length,
            passedVotes: votes.filter(v => v.result && v.result.toLowerCase().includes('pass')).length,
            failedVotes: votes.filter(v => v.result && v.result.toLowerCase().includes('fail')).length,
            agendaItems: votes.map(vote => ({
                item: vote.agenda_item,
                result: vote.result,
                timestamp: vote.video_timestamp
            }))
        };

        // Generate PDF content (would need a PDF library)
        console.log('PDF Export:', summary);
        return summary;
    }

    // Generate shareable links
    static generateShareableLink(type, id) {
        const baseUrl = window.location.origin + window.location.pathname;

        switch(type) {
            case 'meeting':
                return `${baseUrl}#/meeting/${id}`;
            case 'councilmember':
                return `${baseUrl}#/councilmember/${id}`;
            case 'search':
                return `${baseUrl}#/search?q=${encodeURIComponent(id)}`;
            default:
                return baseUrl;
        }
    }

    // Download file helper
    static downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    // Copy to clipboard
    static copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            // Show success message
            this.showNotification('Copied to clipboard!', 'success');
        }).catch(err => {
            console.error('Failed to copy: ', err);
            this.showNotification('Failed to copy to clipboard', 'error');
        });
    }

    // Show notification
    static showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
}
