// HTML Templates for Torrance Vote Viewer

class VoteViewerTemplates {
    // Meeting card template
    static meetingCard(meeting, meetingSummary, utils) {
        return `
            <div class="meeting-card" onclick="app.navigateTo('meeting/${meeting.id}')" style="cursor: pointer;">
                <div class="meeting-header">
                    <div>
                        <div class="meeting-title">${meeting.title}</div>
                        <div class="meeting-date">${utils.formatMeetingDateTime(meeting.date, meeting.time)}</div>
                    </div>
                    <div>
                        <div class="stat-number">${meeting.total_votes}</div>
                        <div class="stat-label">Votes</div>
                    </div>
                </div>

                ${meetingSummary ? this.meetingSummaryPreview(meetingSummary) : ''}

                <div class="meeting-links">
                    <a href="#/meeting/${meeting.id}" class="meeting-link" onclick="event.stopPropagation();">View Votes</a>
                    ${meeting.video_url ? `<a href="${meeting.video_url}" target="_blank" class="meeting-link" onclick="event.stopPropagation();">📹 Watch Video</a>` : ''}
                    ${meeting.agenda_url ? `<a href="${meeting.agenda_url}" target="_blank" class="meeting-link" onclick="event.stopPropagation();">📋 View Agenda</a>` : ''}
                    <button onclick="event.stopPropagation(); app.copyVoteLink('${meeting.id}', '')" class="btn btn-small" title="Copy link to this meeting">
                        🔗 Copy Link
                    </button>
                </div>
            </div>
        `;
    }

    // Meeting summary preview template
    static meetingSummaryPreview(meetingSummary) {
        return `
            <div class="meeting-summary-preview">
                <div class="meeting-summary-preview-title">📋 Meeting Summary</div>
                <div class="meeting-summary-preview-text">${meetingSummary.summary}</div>
                ${meetingSummary.unique_aspects && meetingSummary.unique_aspects.length > 0 ? `
                    <div class="meeting-summary-preview-key">
                        <strong>Key:</strong> ${meetingSummary.unique_aspects.slice(0, 2).join(', ')}
                        ${meetingSummary.unique_aspects.length > 2 ? ` +${meetingSummary.unique_aspects.length - 2} more` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    }

    // Meeting detail template
    static meetingDetail(meeting, votes, meetingSummary, utils) {
        const voteStats = utils.calculateVoteStats(votes);

        return `
            <div class="breadcrumb">
                <a href="#/meetings">Meetings</a> > ${meeting.title}
            </div>

            <div class="meeting-card">
                <div class="meeting-header">
                    <div>
                        <div class="meeting-title">${meeting.title}</div>
                        <div class="meeting-date">${meeting.date}</div>
                    </div>
                    <div>
                        <div class="stat-number">${meeting.total_votes}</div>
                        <div class="stat-label">Votes</div>
                    </div>
                </div>

                <div class="meeting-links">
                    ${meeting.video_url ? `<a href="${meeting.video_url}" target="_blank" class="meeting-link">📹 Watch Video</a>` : ''}
                    ${meeting.agenda_url ? `<a href="${meeting.agenda_url}" target="_blank" class="meeting-link">📋 View Agenda</a>` : ''}
                    <button onclick="app.copyVoteLink('${meeting.id}', '')" class="btn btn-small" title="Copy link to this meeting">
                        🔗 Copy Link
                    </button>
                </div>

                <div class="stats-grid meeting-stats-grid">
                    <div class="stat-card">
                        <div class="stat-number">${voteStats.passed}</div>
                        <div class="stat-label">Passed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${voteStats.failed}</div>
                        <div class="stat-label">Failed</div>
                    </div>
                </div>
            </div>

            ${meetingSummary ? this.meetingSummaryCard(meetingSummary) : ''}

            <h3>Votes (${votes.length})</h3>
            ${this.votesList(votes, utils)}
        `;
    }

    // Meeting summary card template
    static meetingSummaryCard(meetingSummary) {
        return `
            <div class="meeting-summary-card">
                <h3>📋 Meeting Summary</h3>
                <p class="meeting-summary-text">${meetingSummary.summary}</p>

                ${meetingSummary.unique_aspects && meetingSummary.unique_aspects.length > 0 ? `
                    <h4 class="meeting-summary-highlight">Key Highlights:</h4>
                    <ul class="meeting-summary-list">
                        ${meetingSummary.unique_aspects.map(aspect => `<li class="meeting-summary-item">${aspect}</li>`).join('')}
                    </ul>
                ` : ''}

                ${meetingSummary.key_items && meetingSummary.key_items.length > 0 ? `
                    <h4 class="meeting-summary-highlight" style="margin-top: 1rem;">Key Agenda Items:</h4>
                    <ul class="meeting-summary-list">
                        ${meetingSummary.key_items.map(item => `<li class="meeting-summary-item">${item}</li>`).join('')}
                    </ul>
                ` : ''}
            </div>
        `;
    }

    // Vote item template
    static voteItem(vote, utils) {
        const { timestamp, timestampSource } = utils.calculateVoteTimestamp(vote);
        const videoDeepLink = utils.generateVideoDeepLink(vote);
        const agendaDeepLink = utils.generateAgendaDeepLink(vote);

        return `
            <div class="vote-item">
                <div class="vote-header">
                    <span class="vote-agenda-item">${vote.agenda_item || 'No agenda item available'}</span>
                    <span class="vote-result ${vote.result.toLowerCase().includes('pass') ? 'result-passed' : 'result-failed'}">
                        ${vote.result.toLowerCase().includes('pass') ? 'PASSED' : 'FAILED'}
                    </span>
                </div>
                <div class="vote-tally">
                    Ayes: ${vote.vote_tally.ayes} |
                    Noes: ${vote.vote_tally.noes} |
                    Abstentions: ${vote.vote_tally.abstentions}
                </div>
                <div class="vote-timestamp">
                    Vote occurred at ${timestampSource === 'actual' ? '' : 'approximately '}${timestamp} in meeting video
                    ${timestampSource === 'estimated' ? ' (estimated from frame data)' : ''}
                </div>
                ${vote.motion_text ? `<div class="vote-motion-text">${vote.motion_text}</div>` : ''}
                <div class="vote-links">
                    ${videoDeepLink ? `
                        ${timestampSource === 'actual' ? 
                            `<a href="${videoDeepLink}" target="_blank" class="meeting-link">📹 Watch at ${timestamp}</a>` :
                            `<a href="${videoDeepLink}" target="_blank" class="meeting-link">📹 Watch Video</a>`
                        }
                    ` : ''}
                    ${agendaDeepLink ? `<a href="${agendaDeepLink}" target="_blank" class="meeting-link">📋 View Agenda Item</a>` : ''}
                    ${vote.video_url ? `<a href="${vote.video_url}" target="_blank" class="meeting-link">📺 Full Video</a>` : ''}
                </div>
            </div>
        `;
    }

    // Votes list template
    static votesList(votes, utils) {
        return votes.map(vote => this.voteItem(vote, utils)).join('');
    }

    // Councilmember card template (for mayor)
    static councilmemberCard(cm, councilmemberSummary, utils) {
        const fullName = utils.getFullName(cm.id);

        return `
            <div class="councilmember-card councilmember-card-clickable" onclick="app.navigateTo('councilmember/${cm.id}')">
                <div class="councilmember-name">${fullName}</div>
                <div class="councilmember-stats-horizontal">
                    <div class="councilmember-stat">
                        <div class="councilmember-stat-number">${cm.total_votes}</div>
                        <div class="councilmember-stat-label">Total Votes</div>
                    </div>
                    <div class="councilmember-stat">
                        <div class="councilmember-stat-number">${cm.yes_votes}</div>
                        <div class="councilmember-stat-label">Yes Votes</div>
                    </div>
                    <div class="councilmember-stat">
                        <div class="councilmember-stat-number">${cm.no_votes}</div>
                        <div class="councilmember-stat-label">No Votes</div>
                    </div>
                </div>

                ${councilmemberSummary ? this.councilmemberSummaryCard(cm.id, councilmemberSummary, utils, true) : ''}

                <a href="#/councilmember/${cm.id}" class="btn" onclick="event.stopPropagation();">View Details</a>
            </div>
        `;
    }

    // Councilmember row template (for councilmembers list)
    static councilmemberRow(cm, councilmemberSummary, utils) {
        const fullName = utils.getFullName(cm.id);

        return `
            <div class="councilmember-row councilmember-card-clickable" onclick="app.navigateTo('councilmember/${cm.id}')">
                <div class="councilmember-info">
                    <div class="councilmember-name-large">${fullName}</div>
                    <div class="councilmember-stats-horizontal">
                        <div class="councilmember-stat">
                            <div class="councilmember-stat-number">${cm.total_votes}</div>
                            <div class="councilmember-stat-label">Total Votes</div>
                        </div>
                        <div class="councilmember-stat">
                            <div class="councilmember-stat-number">${cm.yes_votes}</div>
                            <div class="councilmember-stat-label">Yes Votes</div>
                        </div>
                        <div class="councilmember-stat">
                            <div class="councilmember-stat-number">${cm.no_votes}</div>
                            <div class="councilmember-stat-label">No Votes</div>
                        </div>
                    </div>
                </div>

                <div class="councilmember-summary-section">
                    ${councilmemberSummary ? this.councilmemberSummaryCard(cm.id, councilmemberSummary, utils, false) : this.councilmemberSummaryPlaceholder()}
                </div>
                <div class="councilmember-actions">
                    <a href="#/councilmember/${cm.id}" class="btn btn-primary" onclick="event.stopPropagation();">View Details</a>
                </div>
            </div>
        `;
    }

    // Councilmember summary card template
    static councilmemberSummaryCard(councilmemberId, councilmemberSummary, utils, isSmall = false) {
        const sizeClass = isSmall ? '' : '-large';
        const previewLength = isSmall ? 120 : 150;
        const cardClass = isSmall ? 'councilmember-summary-card' : 'councilmember-summary-card-large';

        return `
            <div class="${cardClass}">
                <div class="councilmember-profile-title${sizeClass}">👤 ${isSmall ? 'Mayor' : 'Councilmember'} Profile</div>

                <div class="councilmember-summary-preview${sizeClass}">
                    ${councilmemberSummary.summary.length > previewLength ?
            utils.convertMarkdownLinks(councilmemberSummary.summary.substring(0, previewLength)) + '...' :
                        utils.convertMarkdownLinks(councilmemberSummary.summary)
                    }
                </div>

                <details>
                    <summary class="councilmember-summary-details${sizeClass}">
                        ${councilmemberSummary.summary.length > previewLength ? 'Show full profile' : 'Show additional details'}
                    </summary>
                    <div>
                        <div class="councilmember-summary-full${sizeClass}">
                            ${utils.convertMarkdownLinks(councilmemberSummary.summary)}
                        </div>

                        ${councilmemberSummary.bio_url ? `
                            <div class="councilmember-bio-link${sizeClass}">
                                <a href="${councilmemberSummary.bio_url}" target="_blank">
                                    📋 View Official Bio →
                                </a>
                            </div>
                        ` : ''}

                        ${councilmemberSummary.policy_focus && councilmemberSummary.policy_focus.length > 0 ? `
                            <div class="councilmember-policy-focus${sizeClass}">
                                <div class="councilmember-policy-focus-title">Policy Focus Areas:</div>
                                <div class="councilmember-policy-focus-text">
                                    ${councilmemberSummary.policy_focus.join(' • ')}
                                </div>
                            </div>
                        ` : ''}

                        ${councilmemberSummary.notes && councilmemberSummary.notes.length > 0 ? `
                            <div>
                                <div class="councilmember-notes-title">Key Notes:</div>
                                <ul class="councilmember-notes-list">
                                    ${councilmemberSummary.notes.slice(0, 3).map(note => `<li class="councilmember-notes-item">${utils.convertUrlsToLinks(note)}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                    </div>
                </details>
            </div>
        `;
    }

    // Councilmember summary placeholder template
    static councilmemberSummaryPlaceholder() {
        return `
            <div class="councilmember-summary-placeholder">
                Profile summary coming soon...
            </div>
        `;
    }

    // Councilmember detail template
    static councilmemberDetail(councilmember, votes, councilmemberSummary, utils) {
        const fullName = utils.getFullName(councilmember.id);

        return `
            <div class="breadcrumb">
                <a href="#/councilmembers">Councilmembers</a> > ${fullName}
            </div>

            <div class="councilmember-card">
                <div class="councilmember-header">
                    <div class="councilmember-name-large">${fullName}</div>
                    <div class="councilmember-stats-horizontal">
                        <div class="councilmember-stat">
                            <div class="stat-number">${councilmember.total_votes}</div>
                            <div class="stat-label">Total Votes</div>
                        </div>
                        <div class="councilmember-stat">
                            <div class="stat-number">${councilmember.yes_votes}</div>
                            <div class="stat-label">Voted Yes</div>
                        </div>
                        <div class="councilmember-stat">
                            <div class="stat-number">${councilmember.no_votes}</div>
                            <div class="stat-label">Voted No</div>
                        </div>
                    </div>
                </div>

                ${councilmemberSummary ? this.councilmemberProfileSection(councilmemberSummary, utils) : ''}

                <h3>Voting Record</h3>
                ${this.votesList(votes, utils)}
            </div>
        `;
    }

    // Councilmember profile section template
    static councilmemberProfileSection(councilmemberSummary, utils) {
        return `
            <details open>
                <summary>👤 Councilmember Profile</summary>
                <div>
                    <div class="councilmember-profile-section">${utils.convertMarkdownLinks(councilmemberSummary.summary)}</div>

                    ${councilmemberSummary.bio_url ? `
                        <div class="councilmember-profile-bio">
                            <a href="${councilmemberSummary.bio_url}" target="_blank">
                                📋 View Official Bio →
                            </a>
                        </div>
                    ` : ''}

                    ${councilmemberSummary.policy_focus && councilmemberSummary.policy_focus.length > 0 ? `
                        <div class="councilmember-profile-focus">
                            <h4 class="councilmember-profile-focus-title">Policy Focus Areas:</h4>
                            <div class="councilmember-profile-focus-text">
                                ${councilmemberSummary.policy_focus.join(' • ')}
                            </div>
                        </div>
                    ` : ''}

                    ${councilmemberSummary.notable_initiatives && councilmemberSummary.notable_initiatives.length > 0 ? `
                        <div class="councilmember-profile-initiatives">
                            <h4 class="councilmember-profile-initiatives-title">Notable Initiatives:</h4>
                            <ul class="councilmember-profile-initiatives-list">
                                ${councilmemberSummary.notable_initiatives.map(initiative => `<li class="councilmember-profile-initiatives-item">${initiative}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}

                    ${councilmemberSummary.notes && councilmemberSummary.notes.length > 0 ? `
                        <div>
                            <h4 class="councilmember-profile-notes-title">Additional Notes:</h4>
                            <ul class="councilmember-profile-notes-list">
                                ${councilmemberSummary.notes.map(note => `<li class="councilmember-profile-notes-item">${utils.convertUrlsToLinks(note)}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                </div>
            </details>
        `;
    }
}
