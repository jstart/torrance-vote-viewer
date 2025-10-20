// Enhanced UI Components

class EnhancedUI {
    // Interactive vote timeline
    static renderVoteTimeline(votes) {
        return `
            <div class="vote-timeline">
                <h3>Meeting Timeline</h3>
                <div class="timeline-container">
                    ${votes.map((vote, index) => {
                        const timestamp = vote.video_timestamp;
                        const hours = Math.floor(timestamp / 3600);
                        const minutes = Math.floor((timestamp % 3600) / 60);
                        const seconds = timestamp % 60;
                        const timeStr = hours > 0 ?
                            `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}` :
                            `${minutes}:${seconds.toString().padStart(2, '0')}`;

                        return `
                            <div class="timeline-item" data-timestamp="${timestamp}">
                                <div class="timeline-marker"></div>
                                <div class="timeline-content">
                                    <div class="timeline-time">${timeStr}</div>
                                    <div class="timeline-title">${vote.agenda_item}</div>
                                    <div class="timeline-result ${vote.result.toLowerCase()}">${vote.result}</div>
                                    <button onclick="app.jumpToTimestamp(${timestamp})" class="btn btn-small">
                                        Jump to Video
                                    </button>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }

    // Voting pattern visualization
    static renderVotingPatterns(votes) {
        const patterns = this.analyzeVotingPatterns(votes);

        return `
            <div class="voting-patterns">
                <h3>Voting Patterns</h3>
                <div class="pattern-stats">
                    <div class="pattern-stat">
                        <div class="stat-number">${patterns.unanimous}</div>
                        <div class="stat-label">Unanimous Votes</div>
                    </div>
                    <div class="pattern-stat">
                        <div class="stat-number">${patterns.split}</div>
                        <div class="stat-label">Split Votes</div>
                    </div>
                    <div class="pattern-stat">
                        <div class="stat-number">${patterns.controversial}</div>
                        <div class="stat-label">Controversial</div>
                    </div>
                </div>

                <div class="pattern-chart">
                    <canvas id="votingPatternChart" width="400" height="200"></canvas>
                </div>
            </div>
        `;
    }

    // Councilmember comparison tool
    static renderCouncilmemberComparison(councilmembers) {
        return `
            <div class="councilmember-comparison">
                <h3>Councilmember Comparison</h3>
                <div class="comparison-controls">
                    <select id="compareMember1">
                        <option value="">Select First Member</option>
                        ${councilmembers.map(cm =>
                            `<option value="${cm.toLowerCase()}">${cm}</option>`
                        ).join('')}
                    </select>
                    <select id="compareMember2">
                        <option value="">Select Second Member</option>
                        ${councilmembers.map(cm =>
                            `<option value="${cm.toLowerCase()}">${cm}</option>`
                        ).join('')}
                    </select>
                    <button onclick="app.compareCouncilmembers()" class="btn btn-primary">
                        Compare
                    </button>
                </div>
                <div id="comparison-results"></div>
            </div>
        `;
    }

    // Quick stats dashboard
    static renderQuickStats(data) {
        const totalVotes = data.votes.length;
        const totalMeetings = Object.keys(data.meetings).length;
        const avgVotesPerMeeting = Math.round(totalVotes / totalMeetings);

        return `
            <div class="quick-stats">
                <div class="stat-card">
                    <div class="stat-icon">📊</div>
                    <div class="stat-number">${totalVotes}</div>
                    <div class="stat-label">Total Votes</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">🏛️</div>
                    <div class="stat-number">${totalMeetings}</div>
                    <div class="stat-label">Meetings</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">👥</div>
                    <div class="stat-number">${data.councilmembers.length}</div>
                    <div class="stat-label">Councilmembers</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📈</div>
                    <div class="stat-number">${avgVotesPerMeeting}</div>
                    <div class="stat-label">Avg Votes/Meeting</div>
                </div>
            </div>
        `;
    }

    // Mobile-optimized navigation
    static renderMobileNavigation() {
        return `
            <div class="mobile-nav">
                <button class="mobile-nav-toggle" onclick="app.toggleMobileNav()">
                    <span></span>
                    <span></span>
                    <span></span>
                </button>
                <div class="mobile-nav-menu">
                    <a href="#/home" class="mobile-nav-link">🏠 Home</a>
                    <a href="#/meetings" class="mobile-nav-link">📅 Meetings</a>
                    <a href="#/councilmembers" class="mobile-nav-link">👥 Council</a>
                    <a href="#/search" class="mobile-nav-link">🔍 Search</a>
                </div>
            </div>
        `;
    }

    // Analyze voting patterns helper
    static analyzeVotingPatterns(votes) {
        let unanimous = 0;
        let split = 0;
        let controversial = 0;

        votes.forEach(vote => {
            if (vote.individual_votes) {
                const yesCount = vote.individual_votes.filter(v => v.vote === 'yea').length;
                const noCount = vote.individual_votes.filter(v => v.vote === 'nay').length;
                const total = yesCount + noCount;

                if (total > 0) {
                    if (yesCount === total || noCount === total) {
                        unanimous++;
                    } else if (yesCount === noCount) {
                        controversial++;
                    } else {
                        split++;
                    }
                }
            }
        });

        return { unanimous, split, controversial };
    }
}
