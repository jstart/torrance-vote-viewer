// Enhanced Analytics and Visualization Features

class VoteAnalytics {
    // Generate voting patterns analysis
    static generateVotingPatterns(votes, councilmembers) {
        const patterns = {
            unanimousVotes: 0,
            splitVotes: 0,
            controversialVotes: 0,
            attendanceRates: {},
            votingCoalitions: {}
        };

        votes.forEach(vote => {
            if (vote.individual_votes) {
                const individualVotes = vote.individual_votes;
                const yesCount = individualVotes.filter(v => v.vote === 'yea').length;
                const noCount = individualVotes.filter(v => v.vote === 'nay').length;
                const totalVotes = yesCount + noCount;

                if (totalVotes > 0) {
                    if (yesCount === totalVotes || noCount === totalVotes) {
                        patterns.unanimousVotes++;
                    } else if (yesCount === noCount) {
                        patterns.controversialVotes++;
                    } else {
                        patterns.splitVotes++;
                    }
                }
            }
        });

        return patterns;
    }

    // Generate councilmember voting statistics
    static generateCouncilmemberStats(votes, councilmembers) {
        const stats = {};

        councilmembers.forEach(cm => {
            const cmVotes = votes.filter(vote =>
                vote.individual_votes &&
                vote.individual_votes.some(iv => iv.council_member === cm.toLowerCase())
            );

            const yesVotes = cmVotes.filter(vote =>
                vote.individual_votes.some(iv =>
                    iv.council_member === cm.toLowerCase() && iv.vote === 'yea'
                )
            ).length;

            const noVotes = cmVotes.filter(vote =>
                vote.individual_votes.some(iv =>
                    iv.council_member === cm.toLowerCase() && iv.vote === 'nay'
                )
            ).length;

            stats[cm] = {
                totalVotes: cmVotes.length,
                yesVotes: yesVotes,
                noVotes: noVotes,
                attendanceRate: (cmVotes.length / votes.length) * 100,
                yesRate: cmVotes.length > 0 ? (yesVotes / cmVotes.length) * 100 : 0
            };
        });

        return stats;
    }

    // Generate meeting timeline visualization
    static generateMeetingTimeline(meeting) {
        const timeline = [];

        meeting.votes.forEach((vote, index) => {
            timeline.push({
                time: vote.video_timestamp,
                agendaItem: vote.agenda_item,
                result: vote.result,
                duration: index < meeting.votes.length - 1 ?
                    meeting.votes[index + 1].video_timestamp - vote.video_timestamp :
                    null
            });
        });

        return timeline;
    }
}
