// Enhanced Search and Filtering Features

class AdvancedSearch {
    // Multi-criteria search
    static searchVotes(query, filters = {}) {
        const {
            dateRange,
            councilmember,
            voteResult,
            agendaKeywords,
            meetingType
        } = filters;

        return this.data.votes.filter(vote => {
            // Text search in agenda items
            if (query && !vote.agenda_item.toLowerCase().includes(query.toLowerCase())) {
                return false;
            }

            // Date range filter
            if (dateRange && dateRange.start && dateRange.end) {
                const voteDate = new Date(vote.date);
                if (voteDate < dateRange.start || voteDate > dateRange.end) {
                    return false;
                }
            }

            // Councilmember filter
            if (councilmember && vote.individual_votes) {
                const hasMemberVote = vote.individual_votes.some(iv =>
                    iv.council_member === councilmember.toLowerCase()
                );
                if (!hasMemberVote) return false;
            }

            // Vote result filter
            if (voteResult && vote.result !== voteResult) {
                return false;
            }

            // Agenda keywords filter
            if (agendaKeywords && agendaKeywords.length > 0) {
                const hasKeyword = agendaKeywords.some(keyword =>
                    vote.agenda_item.toLowerCase().includes(keyword.toLowerCase())
                );
                if (!hasKeyword) return false;
            }

            return true;
        });
    }

    // Smart suggestions based on search history
    static getSearchSuggestions(query) {
        const suggestions = [];

        // Agenda item suggestions
        const agendaItems = this.data.votes.map(v => v.agenda_item);
        const matchingItems = agendaItems.filter(item =>
            item.toLowerCase().includes(query.toLowerCase())
        );

        suggestions.push(...matchingItems.slice(0, 5));

        // Councilmember suggestions
        const councilmembers = this.data.councilmembers;
        const matchingMembers = councilmembers.filter(cm =>
            cm.toLowerCase().includes(query.toLowerCase())
        );

        suggestions.push(...matchingMembers);

        return [...new Set(suggestions)]; // Remove duplicates
    }

    // Advanced filters UI
    static renderAdvancedFilters() {
        return `
            <div class="advanced-filters">
                <div class="filter-group">
                    <label>Date Range:</label>
                    <input type="date" id="startDate" placeholder="Start Date">
                    <input type="date" id="endDate" placeholder="End Date">
                </div>

                <div class="filter-group">
                    <label>Councilmember:</label>
                    <select id="councilmemberFilter">
                        <option value="">All Councilmembers</option>
                        ${this.data.councilmembers.map(cm =>
                            `<option value="${cm.toLowerCase()}">${cm}</option>`
                        ).join('')}
                    </select>
                </div>

                <div class="filter-group">
                    <label>Vote Result:</label>
                    <select id="voteResultFilter">
                        <option value="">All Results</option>
                        <option value="Passes">Passed</option>
                        <option value="Fails">Failed</option>
                        <option value="Tie">Tied</option>
                    </select>
                </div>

                <div class="filter-group">
                    <label>Keywords:</label>
                    <input type="text" id="keywordFilter" placeholder="e.g., planning, budget, ordinance">
                </div>

                <button onclick="app.applyAdvancedFilters()" class="btn btn-primary">
                    Apply Filters
                </button>
                <button onclick="app.clearFilters()" class="btn btn-secondary">
                    Clear All
                </button>
            </div>
        `;
    }
}
