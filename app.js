// Torrance Vote Viewer Application Logic

class TorranceVoteViewer {
    constructor() {
        this.data = null;
        this.currentRoute = null;
        this.init();
    }

    async init() {
        try {
            console.log('Initializing app...');
            await this.loadData();
            this.setupRouting();
            this.setupMobileOptimizations();

            // Handle server-side routes by converting them to hash routes
            this.handleServerSideRoute();

            // Always handle the initial route after setup
            console.log('Handling initial route...');
            this.handleRoute();
        } catch (error) {
            console.error('Error initializing app:', error);
            this.showError('Failed to load data. Please refresh the page.');
        }
    }

    handleServerSideRoute() {
        const pathname = window.location.pathname;
        const hash = window.location.hash;

        // If we have a server-side route but no hash, convert it
        if (pathname !== '/' && pathname !== '/index.html' && !hash) {
            console.log('Converting server-side route to hash route:', pathname);
            const newHash = '#' + pathname;
            window.history.replaceState({}, '', window.location.origin + newHash);
        }
    }

    async loadData() {
        console.log('Loading data from torrance_votes_smart_consolidated.json...');
        // Use absolute path to avoid issues with different base paths
        const dataPath = window.location.pathname.includes('/') && !window.location.pathname.endsWith('/')
            ? '/data/torrance_votes_smart_consolidated.json'
            : 'data/torrance_votes_smart_consolidated.json';
        console.log('Using data path:', dataPath);

        // Add cache-busting parameter
        const cacheBuster = '?v=' + Date.now();
        const response = await fetch(dataPath + cacheBuster);
        console.log('Response status:', response.status);
        if (!response.ok) {
            throw new Error(`Failed to load data: ${response.status} ${response.statusText}`);
        }
        this.data = await response.json();
        console.log('Data loaded successfully:', this.data.metadata);
        console.log('Has meeting_summaries:', 'meeting_summaries' in this.data);
        console.log('Has councilmember_summaries:', 'councilmember_summaries' in this.data);
        console.log('Has councilmember_stats:', 'councilmember_stats' in this.data);
        console.log('Votes with individual data:', this.data.votes?.filter(v => v.individual_votes)?.length || 0);
        console.log('Meeting summaries count:', Object.keys(this.data.meeting_summaries || {}).length);
        console.log('Councilmember summaries count:', Object.keys(this.data.councilmember_summaries || {}).length);
    }

    setupRouting() {
        console.log('Setting up routing...');

        // Handle browser back/forward
        window.addEventListener('popstate', () => {
            console.log('popstate event triggered');
            this.handleRoute();
        });

        // Handle hash changes
        window.addEventListener('hashchange', () => {
            console.log('hashchange event triggered, hash:', window.location.hash);
            this.handleRoute();
        });

        // Handle navigation clicks
        document.addEventListener('click', (e) => {
            if (e.target.matches('[data-route]')) {
                e.preventDefault();
                const route = e.target.getAttribute('data-route');
                const href = e.target.getAttribute('href');

                // If href exists and contains more than just the route, use it
                if (href && href.includes('/') && href.split('/').length > 2) {
                    console.log('Data route with href clicked:', href);
                    window.location.hash = href; // href already includes #
                    this.handleRoute();
                } else {
                    console.log('Data route clicked:', route);
                    this.navigateTo(route);
                }
            } else if (e.target.matches('a[href^="#/"]')) {
                // Handle hash-based navigation links
                e.preventDefault();
                const href = e.target.getAttribute('href');
                console.log('Hash link clicked:', href);
                window.location.hash = href; // href already includes #
                this.handleRoute();
            }
        });
    }

    navigateTo(route) {
        window.history.pushState({}, '', `#/${route}`);
        this.handleRoute();
    }

    handleRoute() {
        const rawHash = window.location.hash.slice(1);
        // Normalize leading slashes so '#/meeting/14490' -> 'meeting/14490'
        const hash = rawHash.replace(/^\/+/, '');
        const parts = hash.split('/');
        console.log('handleRoute called with hash:', hash, 'parts:', parts);
        console.log('Data loaded:', !!this.data);
        console.log('Meetings available:', this.data ? Object.keys(this.data.meetings) : 'No data');

        // Update active nav link
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

        let activeLink = document.querySelector(`[data-route="${parts[0] || 'home'}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }

        // Route handling
        console.log('Routing to:', parts[0]);
        switch (parts[0]) {
            case '':
            case 'home':
                this.showHome();
                break;
            case 'meetings':
                this.showMeetings();
                break;
            case 'meeting':
                if (parts[1]) {
                    this.showMeeting(parts[1]);
                } else {
                    this.showMeetings();
                }
                break;
            case 'councilmembers':
                this.showCouncilmembers();
                break;
            case 'councilmember':
                if (parts[1]) {
                    this.showCouncilmember(parts[1]);
                } else {
                    this.showCouncilmembers();
                }
                break;
            case 'year':
                if (parts[1]) {
                    this.showYear(parts[1]);
                } else {
                    this.showHome();
                }
                break;
            case 'search':
                this.showSearch();
                break;
            default:
                this.showHome();
        }
    }

    showHome() {
        const stats = this.data.metadata;
        const content = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">${stats.total_votes}</div>
                    <div class="stat-label">Total Votes</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${stats.total_meetings}</div>
                    <div class="stat-label">Meetings</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${stats.total_councilmembers}</div>
                    <div class="stat-label">Councilmembers</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${stats.total_agenda_items}</div>
                    <div class="stat-label">Agenda Items</div>
                </div>
            </div>

            <div class="data-freshness">
                <small>📅 Data last updated: ${new Date().toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}</small>
            </div>

            <h2>Recent Meetings</h2>
            ${this.renderMeetingsList(Object.values(this.data.meetings).slice(0, 3))}

            <h2>Quick Links</h2>
            <div class="nav-links">
                <a href="#/meetings" class="nav-link">View All Meetings</a>
                <a href="#/councilmembers" class="nav-link">View Councilmembers</a>
                <a href="#/search" class="nav-link">Search Votes</a>
            </div>


            <h2>Export Data</h2>
            <div class="export-section">
                <p>Download all vote data for analysis or archival purposes.</p>
                <div class="export-buttons">
                    <button onclick="app.exportData('csv')" class="btn btn-primary">
                        📊 Download CSV
                    </button>
                    <button onclick="app.exportData('json')" class="btn btn-secondary">
                        📄 Download JSON
                    </button>
                </div>
                <div class="export-info">
                    <small>CSV format is ideal for spreadsheet analysis. JSON format preserves all data structure.</small>
                </div>
            </div>

            <!-- Email subscription feature temporarily disabled
            <h2>Stay Updated</h2>
            <div class="subscription-section">
                <p>Get notified when new meetings are added to the system.</p>
                <div class="subscription-form">
                    <input type="email" id="emailInput" placeholder="Enter your email address" class="email-input">
                    <button onclick="app.subscribeToUpdates()" class="btn btn-primary">
                        📧 Subscribe
                    </button>
                </div>
                <div class="subscription-info">
                    <small>We'll send you a notification when new meeting data is available. Unsubscribe anytime.</small>
                </div>
            </div>
            -->
        `;
        this.renderContent(content);
    }

    showMeetings() {
        const meetings = Object.values(this.data.meetings);
        const content = `
            <h2>All Meetings</h2>
            ${this.renderMeetingsList(meetings)}
        `;
        this.renderContent(content);
    }

    showMeeting(meetingId) {
        console.log('showMeeting called with ID:', meetingId, 'type:', typeof meetingId);
        console.log('Available meetings:', Object.keys(this.data.meetings));

        const meeting = this.data.meetings[meetingId];
        if (!meeting) {
            console.log('Meeting not found:', meetingId);
            console.log('Trying with string conversion...');
            const meetingStr = String(meetingId);
            const meetingStrCheck = this.data.meetings[meetingStr];
            if (meetingStrCheck) {
                console.log('Found meeting with string conversion:', meetingStr);
                this.showMeetingDetail(meetingStr, meetingStrCheck);
                return;
            }
            this.showError(`Meeting not found: ${meetingId}`);
            return;
        }

        this.showMeetingDetail(meetingId, meeting);
    }

    showMeetingDetail(meetingId, meeting) {
        console.log('showMeetingDetail called for:', meetingId);
        console.log('Found meeting:', meeting);
        const votes = this.data.votes.filter(vote => vote.meeting_id === meetingId)
            .sort((a, b) => (a.frame_number || 0) - (b.frame_number || 0));

        // Get meeting summary if available
        const meetingSummary = this.data.meeting_summaries && this.data.meeting_summaries[meetingId];
        console.log('Meeting summary for', meetingId, ':', meetingSummary);

        const content = `
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
                </div>

                <div class="stats-grid meeting-stats-grid">
                    <div class="stat-card">
                        <div class="stat-number">${votes.filter(v => v.result && v.result.toLowerCase().includes('pass')).length}</div>
                        <div class="stat-label">Passed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${votes.filter(v => v.result && v.result.toLowerCase().includes('fail')).length}</div>
                        <div class="stat-label">Failed</div>
                    </div>
                </div>
            </div>

            ${meetingSummary ? `
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
            ` : ''}

            <h3>Votes (${votes.length})</h3>
            ${this.renderVotesList(votes)}
        `;
        this.renderContent(content);
    }

    showCouncilmembers() {
        // Get councilmembers from the new data structure
        const councilmemberNames = this.data.councilmembers || [];

        // Create councilmember objects with stats
        const councilmembers = councilmemberNames.map(name => ({
            id: name.toLowerCase(),
            display_name: name,
            total_votes: this.data.councilmember_stats?.[name]?.total_votes || 0,
            yes_votes: this.data.councilmember_stats?.[name]?.yes_votes || 0,
            no_votes: this.data.councilmember_stats?.[name]?.no_votes || 0
        }));

        // Define full names and identify mayors
        const fullNames = {
            'chen': 'Chen',
            'gerson': 'Gerson',
            'kaji': 'Kaji',
            'kalani': 'Kalani',
            'lewis': 'Lewis',
            'mattucci': 'Mattucci',
            'sheikh': 'Sheikh'
        };

        // Separate mayors
        const mayors = councilmembers.filter(cm => cm.id === 'chen');
        const councilmembersList = councilmembers.filter(cm => cm.id !== 'chen');

        const content = `
            <h2>City Council</h2>

            ${mayors.length > 0 ? `
                <h3>Mayor</h3>
                <div class="stats-grid">
                    ${mayors.map(cm => {
                        const councilmemberSummary = this.data.councilmember_summaries && this.data.councilmember_summaries[fullNames[cm.id]];
                        return `
                            <div class="councilmember-card" onclick="app.navigateTo('councilmember/${cm.id}')" style="cursor: pointer;">
                                <div class="councilmember-name">${fullNames[cm.id] || cm.display_name}</div>
                                <div class="councilmember-stats-horizontal">
                                    <div class="councilmember-stat">
                                        <div class="councilmember-stat-number">${this.data.councilmember_stats?.[fullNames[cm.id]]?.total_votes || 0}</div>
                                        <div class="councilmember-stat-label">Total Votes</div>
                                    </div>
                                    <div class="councilmember-stat">
                                        <div class="councilmember-stat-number">${this.data.councilmember_stats?.[fullNames[cm.id]]?.yes_votes || 0}</div>
                                        <div class="councilmember-stat-label">Yes Votes</div>
                                    </div>
                                    <div class="councilmember-stat">
                                        <div class="councilmember-stat-number">${this.data.councilmember_stats?.[fullNames[cm.id]]?.no_votes || 0}</div>
                                        <div class="councilmember-stat-label">No Votes</div>
                                    </div>
                                </div>

                                ${councilmemberSummary ? `
                                    <div style="background: #f8f9fa; padding: 0.8rem; border-radius: 6px; margin: 0.8rem 0; border-left: 3px solid #1976d2; font-size: 0.85rem;">
                                        <div style="font-weight: bold; color: #1976d2; margin-bottom: 0.3rem;">👤 Mayor Profile</div>

                                        <!-- Preview text (first ~120 characters) -->
                                        <div style="line-height: 1.3; margin-bottom: 0.6rem;">
                                            ${councilmemberSummary.summary.length > 120 ?
                            councilmemberSummary.summary.substring(0, 120).replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href=\"$2\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>') + '...' :
                                                councilmemberSummary.summary.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href=\"$2\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>')
                                            }
                                        </div>

                                        <!-- Expandable details -->
                                        <details>
                                            <summary style="font-size: 0.8rem; color: #1976d2; cursor: pointer; margin-bottom: 0.6rem;">
                                                ${councilmemberSummary.summary.length > 120 ? 'Show full profile' : 'Show additional details'}
                                            </summary>
                                            <div>
                                                <!-- Full summary text -->
                                                <div style="line-height: 1.3; margin-bottom: 0.6rem;">
                                                    ${councilmemberSummary.summary.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href=\"$2\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>')}
                                                </div>

                                                ${councilmemberSummary.bio_url ? `
                                                    <div style="margin-bottom: 0.6rem;">
                                                        <a href="${councilmemberSummary.bio_url}" target="_blank" style="color: #1976d2; text-decoration: none; font-weight: bold; font-size: 0.8rem;">
                                                            📋 View Official Bio →
                                                        </a>
                                                    </div>
                                                ` : ''}

                                                ${councilmemberSummary.policy_focus && councilmemberSummary.policy_focus.length > 0 ? `
                                                    <div style="font-size: 0.8rem; color: #666;">
                                                        <strong>Focus:</strong> ${councilmemberSummary.policy_focus.slice(0, 2).join(' • ')}
                                                    </div>
                                                ` : ''}
                                            </div>
                                        </details>
                                    </div>
                                ` : ''}

                                <a href="#/councilmember/${cm.id}" class="btn" onclick="event.stopPropagation();">View Details</a>
                            </div>
                        `;
                    }).join('')}
                </div>
            ` : ''}

            <h3>Councilmembers</h3>
            <div class="councilmembers-list">
                ${councilmembersList.map(cm => {
                    const councilmemberSummary = this.data.councilmember_summaries && this.data.councilmember_summaries[fullNames[cm.id]];
                    return `
                        <div class="councilmember-row" onclick="app.navigateTo('councilmember/${cm.id}')" style="cursor: pointer;">
                            <div class="councilmember-info">
                                <div class="councilmember-name-large">${fullNames[cm.id] || cm.display_name}</div>
                                <div class="councilmember-stats-horizontal">
                                    <div class="councilmember-stat">
                                        <div class="councilmember-stat-number">${this.data.councilmember_stats?.[fullNames[cm.id]]?.total_votes || 0}</div>
                                        <div class="councilmember-stat-label">Total Votes</div>
                                    </div>
                                    <div class="councilmember-stat">
                                        <div class="councilmember-stat-number">${this.data.councilmember_stats?.[fullNames[cm.id]]?.yes_votes || 0}</div>
                                        <div class="councilmember-stat-label">Yes Votes</div>
                                    </div>
                                    <div class="councilmember-stat">
                                        <div class="councilmember-stat-number">${this.data.councilmember_stats?.[fullNames[cm.id]]?.no_votes || 0}</div>
                                        <div class="councilmember-stat-label">No Votes</div>
                                    </div>
                                </div>
                            </div>

                            <div class="councilmember-summary-section">
                                ${councilmemberSummary ? `
                                    <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; margin: 1rem 0; border-left: 4px solid #1976d2;">
                                        <div style="font-weight: bold; color: #1976d2; margin-bottom: 0.5rem; font-size: 0.9rem;">👤 Councilmember Profile</div>

                                        <!-- Preview text (first ~150 characters) -->
                                        <div style="line-height: 1.4; font-size: 0.9rem; margin-bottom: 0.8rem;">
                                            ${councilmemberSummary.summary.length > 150 ?
                        councilmemberSummary.summary.substring(0, 150).replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href=\"$2\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>') + '...' :
                                                councilmemberSummary.summary.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href=\"$2\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>')
                                            }
                                        </div>

                                        <!-- Expandable details -->
                                        <details>
                                            <summary style="font-size: 0.85rem; color: #1976d2; cursor: pointer; margin-bottom: 0.8rem;">
                                                ${councilmemberSummary.summary.length > 150 ? 'Show full profile' : 'Show additional details'}
                                            </summary>
                                            <div>
                                                <!-- Full summary text -->
                                                <div style="line-height: 1.4; font-size: 0.9rem; margin-bottom: 0.8rem;">
                                                    ${councilmemberSummary.summary.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href=\"$2\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>')}
                                                </div>

                                                ${councilmemberSummary.bio_url ? `
                                                    <div style="margin-bottom: 0.8rem;">
                                                        <a href="${councilmemberSummary.bio_url}" target="_blank" style="color: #1976d2; text-decoration: none; font-weight: bold; font-size: 0.85rem;">
                                                            📋 View Official Bio →
                                                        </a>
                                                    </div>
                                                ` : ''}

                                                ${councilmemberSummary.policy_focus && councilmemberSummary.policy_focus.length > 0 ? `
                                                    <div style="margin-bottom: 0.8rem;">
                                                        <div style="font-weight: bold; color: #1976d2; margin-bottom: 0.3rem; font-size: 0.85rem;">Policy Focus Areas:</div>
                                                        <div style="font-size: 0.85rem; color: #666;">
                                                            ${councilmemberSummary.policy_focus.join(' • ')}
                                                        </div>
                                                    </div>
                                                ` : ''}

                                                ${councilmemberSummary.notes && councilmemberSummary.notes.length > 0 ? `
                                                    <div>
                                                        <div style="font-weight: bold; color: #1976d2; margin-bottom: 0.3rem; font-size: 0.85rem;">Key Notes:</div>
                                                        <ul style="margin-left: 1rem; font-size: 0.85rem;">
                                                            ${councilmemberSummary.notes.slice(0, 3).map(note => `<li style="margin-bottom: 0.2rem;">${note.replace(/(https?:\/\/[^\s]+)/g, '<a href=\"$1\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>')}</li>`).join('')}
                                                        </ul>
                                                    </div>
                                                ` : ''}
                                            </div>
                                        </details>
                                    </div>
                                ` : `
                                    <div class="councilmember-summary-placeholder" style="background: #f5f5f5; padding: 1.2rem; border-radius: 8px; margin: 1rem 0; border-left: 4px solid #ccc; color: #666; font-style: italic;">
                                        Profile summary coming soon...
                                    </div>
                                `}
                            </div>
                            <div class="councilmember-actions">
                                <a href="#/councilmember/${cm.id}" class="btn btn-primary" onclick="event.stopPropagation();">View Details</a>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        this.renderContent(content);
    }

    showCouncilmember(councilmemberId) {
        // Get councilmembers from the array and create objects with stats
        const councilmemberNames = this.data.councilmembers || [];
        const councilmembers = councilmemberNames.map(name => ({
            id: name.toLowerCase(),
            display_name: name,
            total_votes: this.data.councilmember_stats?.[name]?.total_votes || 0,
            yes_votes: this.data.councilmember_stats?.[name]?.yes_votes || 0,
            no_votes: this.data.councilmember_stats?.[name]?.no_votes || 0
        }));

        const councilmember = councilmembers.find(cm => cm.id === councilmemberId);
        if (!councilmember) {
            this.showError('Councilmember not found');
            return;
        }

        // Define full names
        const fullNames = {
            'chen': 'Chen',
            'gerson': 'Gerson',
            'kaji': 'Kaji',
            'kalani': 'Kalani',
            'lewis': 'Lewis',
            'mattucci': 'Mattucci',
            'sheikh': 'Sheikh'
        };

        const fullName = fullNames[councilmemberId] || councilmember.display_name;
        const votes = this.data.votes.filter(vote =>
            vote.individual_votes &&
            vote.individual_votes.some(vote_detail =>
                (vote_detail.name || '').toLowerCase() === councilmember.display_name.toLowerCase()
            )
        );

        // Get councilmember summary if available
        const councilmemberSummary = this.data.councilmember_summaries && this.data.councilmember_summaries[fullName];
        console.log('Councilmember summary for', councilmemberId, '->', fullName, ':', councilmemberSummary);

        const content = `
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

                ${councilmemberSummary ? `
                    <details open>
                        <summary>👤 Councilmember Profile</summary>
                        <div>
                            <div style="line-height: 1.6; font-size: 1.1rem; margin-bottom: 1rem;">${councilmemberSummary.summary.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href=\"$2\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>')}</div>

                            ${councilmemberSummary.bio_url ? `
                                <div style="margin-bottom: 1rem;">
                                    <a href="${councilmemberSummary.bio_url}" target="_blank" style="color: #1976d2; text-decoration: none; font-weight: bold; font-size: 1rem;">
                                        📋 View Official Bio →
                                    </a>
                                </div>
                            ` : ''}

                            ${councilmemberSummary.policy_focus && councilmemberSummary.policy_focus.length > 0 ? `
                                <div style="margin-bottom: 1rem;">
                                    <h4 style="margin-bottom: 0.5rem; color: #1976d2;">Policy Focus Areas:</h4>
                                    <div style="font-size: 1rem; color: #666;">
                                        ${councilmemberSummary.policy_focus.join(' • ')}
                                    </div>
                                </div>
                            ` : ''}

                            ${councilmemberSummary.notable_initiatives && councilmemberSummary.notable_initiatives.length > 0 ? `
                                <div style="margin-bottom: 1rem;">
                                    <h4 style="margin-bottom: 0.5rem; color: #1976d2;">Notable Initiatives:</h4>
                                    <ul style="margin-left: 1.5rem;">
                                        ${councilmemberSummary.notable_initiatives.map(initiative => `<li style="margin-bottom: 0.5rem;">${initiative}</li>`).join('')}
                                    </ul>
                                </div>
                            ` : ''}

                            ${councilmemberSummary.notes && councilmemberSummary.notes.length > 0 ? `
                                <div>
                                    <h4 style="margin-bottom: 0.5rem; color: #1976d2;">Additional Notes:</h4>
                                    <ul style="margin-left: 1.5rem;">
                                        ${councilmemberSummary.notes.map(note => `<li style="margin-bottom: 0.5rem;">${note.replace(/(https?:\/\/[^\s]+)/g, '<a href=\"$1\" target=\"_blank\" style=\"color: #1976d2; text-decoration: none; font-weight: bold;\">$1</a>')}</li>`).join('')}
                                    </ul>
                                </div>
                            ` : ''}
                        </div>
                    </details>
                ` : ''}

                <h3>Voting Record</h3>
                ${this.renderVotesList(votes)}
            `;
            this.renderContent(content);
    }

    showYear(year) {
        const meetings = Object.values(this.data.meetings).filter(meeting => meeting.year === year);
        const votes = this.data.votes.filter(vote => vote.year === year);

        const content = `
            <div class="breadcrumb">
                <a href="#/home">Home</a> > Year ${year}
            </div>

            <h2>${year} Meetings</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">${meetings.length}</div>
                    <div class="stat-label">Meetings</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${votes.length}</div>
                    <div class="stat-label">Total Votes</div>
                </div>
            </div>

            ${this.renderMeetingsList(meetings)}
        `;
        this.renderContent(content);
    }

    showSearch() {
        const content = `
            <h2>Search Votes</h2>

            <div class="search-section">
                <input type="text" id="searchInput" class="search-input" placeholder="Search votes by agenda item or motion text...">

                <div class="filter-row">
                    <select id="councilmemberFilter" class="filter-select">
                        <option value="">All Councilmembers</option>
                        ${this.data.councilmembers.map(cm => {
                            const fullNames = {
                                'chen': 'Chen',
                                'gerson': 'Gerson',
                                'kaji': 'Kaji',
                                'kalani': 'Kalani',
                                'lewis': 'Lewis',
                                'mattucci': 'Mattucci',
                                'sheikh': 'Sheikh'
                            };
                            return `<option value="${cm}">${fullNames[cm.toLowerCase()] || cm}</option>`;
                        }).join('')}
                    </select>

                    <select id="meetingFilter" class="filter-select">
                        <option value="">All Meetings</option>
                        ${Object.values(this.data.meetings).map(meeting =>
                            `<option value="${meeting.id}">${meeting.title} (${meeting.date})</option>`
                        ).join('')}
                    </select>

                    <select id="resultFilter" class="filter-select">
                        <option value="">All Results</option>
                        <option value="passed">Passed</option>
                        <option value="failed">Failed</option>
                    </select>

                    <button class="btn" onclick="app.searchVotes()">Search</button>
                    <button class="btn btn-secondary" onclick="app.clearSearch()">Clear</button>
                </div>
            </div>

            <div id="searchResults">                    </div>
        `;
        this.renderContent(content);

        // Add event listener for return key on search input
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.searchVotes();
                }
            });
        }
    }

    searchVotes() {
        const searchTerm = document.getElementById('searchInput').value;
        const councilmember = document.getElementById('councilmemberFilter').value;
        const meeting = document.getElementById('meetingFilter').value;
        const result = document.getElementById('resultFilter').value;

        let votes = this.data.votes;

        // Apply filters
        if (councilmember) {
            votes = votes.filter(vote =>
                vote.individual_votes &&
                vote.individual_votes.some(vote_detail =>
                    (vote_detail.name || '').toLowerCase().includes(councilmember.toLowerCase())
                )
            );
        }

        if (meeting) {
            votes = votes.filter(vote => vote.meeting_id === meeting);
        }

        if (result) {
            const res = (vote) => (vote.result || '').toLowerCase();
            if (result === 'passed') {
                votes = votes.filter(vote => res(vote).includes('pass'));
            } else if (result === 'failed') {
                votes = votes.filter(vote => res(vote).includes('fail'));
            }
        }

        // Apply text search
        if (searchTerm) {
            votes = votes.filter(vote =>
                (vote.agenda_item && vote.agenda_item.toLowerCase().includes(searchTerm.toLowerCase())) ||
                (vote.motion_text && vote.motion_text.toLowerCase().includes(searchTerm.toLowerCase()))
            );
        }

        const resultsDiv = document.getElementById('searchResults');
        if (votes.length === 0) {
            resultsDiv.innerHTML = '<div class="loading">No votes found matching your criteria.</div>';
        } else {
            resultsDiv.innerHTML = `
                <h3>Found ${votes.length} votes</h3>
                ${this.renderVotesList(votes)}
            `;
        }
    }

    clearSearch() {
        document.getElementById('searchInput').value = '';
        document.getElementById('councilmemberFilter').value = '';
        document.getElementById('meetingFilter').value = '';
        document.getElementById('resultFilter').value = '';
        document.getElementById('searchResults').innerHTML = '';
    }

    renderMeetingsList(meetings) {
        return meetings.map(meeting => {
            // Get meeting summary if available
            const meetingSummary = this.data.meeting_summaries && this.data.meeting_summaries[meeting.id];

          // Use the template function
          return VoteViewerTemplates.meetingCard(meeting, meetingSummary, VoteViewerUtils);
        }).join('');
    }

    renderVotesList(votes) {
      return VoteViewerTemplates.votesList(votes, VoteViewerUtils);
    }

    renderContent(content) {
        document.getElementById('content').innerHTML = content;
    }

    showError(message) {
        this.renderContent(`<div class="error">${message}</div>`);
    }

    // Export data functionality
    exportData(format) {
        try {
            const votes = this.data.votes;
            const timestamp = new Date().toISOString().split('T')[0]; // YYYY-MM-DD format

            if (format === 'csv') {
                const filename = `torrance_votes_${timestamp}.csv`;
                VoteViewerUtils.exportToCSV(votes, filename);
                VoteViewerUtils.showNotification('CSV file downloaded successfully!', 'success');
            } else if (format === 'json') {
                const filename = `torrance_votes_${timestamp}.json`;
                VoteViewerUtils.exportToJSON(votes, filename);
                VoteViewerUtils.showNotification('JSON file downloaded successfully!', 'success');
            }
        } catch (error) {
            console.error('Export error:', error);
            VoteViewerUtils.showNotification('Export failed. Please try again.', 'error');
        }
    }

    // Email subscription functionality
    subscribeToUpdates() {
        const emailInput = document.getElementById('emailInput');
        const email = emailInput?.value?.trim();

        if (!email) {
            VoteViewerUtils.showNotification('Please enter a valid email address.', 'error');
            return;
        }

        if (!this.isValidEmail(email)) {
            VoteViewerUtils.showNotification('Please enter a valid email address.', 'error');
            return;
        }

        // Store subscription in localStorage (in a real app, this would go to a server)
        try {
            const subscriptions = this.getStoredSubscriptions();
            if (!subscriptions.includes(email)) {
                subscriptions.push(email);
                localStorage.setItem('torrance_vote_subscriptions', JSON.stringify(subscriptions));
                VoteViewerUtils.showNotification('Successfully subscribed! You\'ll be notified of new meetings.', 'success');
                emailInput.value = ''; // Clear the input
            } else {
                VoteViewerUtils.showNotification('This email is already subscribed.', 'info');
            }
        } catch (error) {
            console.error('Subscription error:', error);
            VoteViewerUtils.showNotification('Subscription failed. Please try again.', 'error');
        }
    }

    // Helper methods for subscription
    isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    getStoredSubscriptions() {
        try {
            const stored = localStorage.getItem('torrance_vote_subscriptions');
            return stored ? JSON.parse(stored) : [];
        } catch (error) {
            console.error('Error reading subscriptions:', error);
            return [];
        }
    }

    // Method to notify subscribers (would be called when new data is added)
    notifySubscribers(newMeetings) {
        const subscriptions = this.getStoredSubscriptions();
        if (subscriptions.length === 0) return;

        // In a real implementation, this would send emails via a server
        console.log(`Notifying ${subscriptions.length} subscribers about ${newMeetings.length} new meetings`);

        // For demo purposes, show a notification
        VoteViewerUtils.showNotification(
          `New meetings detected! ${subscriptions.length} subscribers will be notified.`,
            'info'
        );
    }

    // Copy vote link to clipboard
    copyVoteLink(meetingId, agendaItem) {
        const baseUrl = window.location.origin + window.location.pathname;
        const voteLink = `${baseUrl}#/meeting/${meetingId}`;

        if (navigator.clipboard) {
            navigator.clipboard.writeText(voteLink).then(() => {
                VoteViewerUtils.showNotification('Link copied to clipboard!', 'success');
            }).catch(() => {
                this.fallbackCopyToClipboard(voteLink);
            });
        } else {
            this.fallbackCopyToClipboard(voteLink);
        }
    }

    // Fallback copy method for older browsers
    fallbackCopyToClipboard(text) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            document.execCommand('copy');
            VoteViewerUtils.showNotification('Link copied to clipboard!', 'success');
        } catch (err) {
            VoteViewerUtils.showNotification('Failed to copy link', 'error');
        }
        
        document.body.removeChild(textArea);
    }

    // Mobile-specific optimizations
    setupMobileOptimizations() {
        // Add viewport meta tag if not present
        if (!document.querySelector('meta[name="viewport"]')) {
            const viewport = document.createElement('meta');
            viewport.name = 'viewport';
            viewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
            document.head.appendChild(viewport);
        }

        // Prevent zoom on double tap for iOS
        let lastTouchEnd = 0;
        document.addEventListener('touchend', function (event) {
            const now = (new Date()).getTime();
            if (now - lastTouchEnd <= 300) {
                event.preventDefault();
            }
            lastTouchEnd = now;
        }, false);

        // Add touch feedback for interactive elements
        this.addTouchFeedback();

        // Optimize scrolling performance
        this.optimizeScrolling();

        // Handle orientation changes
        window.addEventListener('orientationchange', () => {
            setTimeout(() => {
                this.handleRoute(); // Refresh current view after orientation change
            }, 100);
        });
    }

    // Add visual feedback for touch interactions
    addTouchFeedback() {
        const touchElements = document.querySelectorAll('.btn, .nav-link, .meeting-link, .vote-item, .meeting-card, .councilmember-card, .councilmember-row');
        
        touchElements.forEach(element => {
            element.addEventListener('touchstart', function() {
                this.style.transform = 'scale(0.98)';
                this.style.opacity = '0.8';
            });
            
            element.addEventListener('touchend', function() {
                this.style.transform = '';
                this.style.opacity = '';
            });
            
            element.addEventListener('touchcancel', function() {
                this.style.transform = '';
                this.style.opacity = '';
            });
        });
    }

    // Optimize scrolling performance
    optimizeScrolling() {
        // Add smooth scrolling behavior
        document.documentElement.style.scrollBehavior = 'smooth';
        
        // Optimize scroll performance on mobile
        let ticking = false;
        
        function updateScrollPosition() {
            // Add any scroll-based optimizations here
            ticking = false;
        }
        
        function requestTick() {
            if (!ticking) {
                requestAnimationFrame(updateScrollPosition);
                ticking = true;
            }
        }
        
        window.addEventListener('scroll', requestTick, { passive: true });
    }
}

// Initialize the app
function initializeApp() {
    console.log('Initializing TorranceVoteViewer...');
    try {
        const app = new TorranceVoteViewer();
        window.app = app;
        console.log('TorranceVoteViewer initialized successfully');
        return true;
    } catch (error) {
        console.error('Error initializing TorranceVoteViewer:', error);
        document.getElementById('content').innerHTML = `
            <div class="error">
                <h3>Error Loading Application</h3>
                <p>There was an error loading the vote viewer. Please refresh the page.</p>
                <p>Error: ${error.message}</p>
            </div>
        `;
        return false;
    }
}

// Try multiple initialization strategies
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}

// Fallback initialization after a short delay
setTimeout(() => {
    if (!window.app) {
        console.log('Fallback initialization...');
        initializeApp();
    }
}, 100);
