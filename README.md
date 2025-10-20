# Torrance Vote Viewer

A comprehensive web application for browsing and analyzing Torrance City Council votes, meetings, and councilmember records.

## 🌟 Features

- **Meeting Browser**: View all City Council meetings with summaries and vote counts
- **Vote Analysis**: Detailed vote records with timestamps and deep links to video
- **Councilmember Profiles**: Individual councilmember voting records and profiles
- **Advanced Search**: Filter votes by councilmember, meeting, result, or text search
- **Year-based Navigation**: Browse meetings and votes by year
- **Deep Linking**: Direct links to specific video timestamps and agenda items
- **Responsive Design**: Mobile-friendly interface

## 🚀 Live Demo

Visit the live application at: [https://truman4congress.com/torrance-vote-viewer/](https://truman4congress.com/torrance-vote-viewer/)

## 📁 Project Structure

```
torrance-vote-viewer/
├── index.html              # Main HTML file
├── styles.css              # All CSS styles
├── app.js                  # Main application logic
├── utils.js                # Utility functions
├── templates.js            # HTML template functions
├── data/                   # JSON data files
│   ├── torrance_votes_smart_consolidated.json
│   ├── meta_id_mapping.json
│   └── video_timestamps.json
├── merge_meta_ids.py       # Script to merge meta IDs
├── scrape_timestamps.py    # Script to scrape video timestamps
└── README.md              # This file
```

## 🛠️ Technical Stack

- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Data**: JSON files with consolidated vote data
- **Deployment**: GitHub Pages (static hosting)
- **Routing**: Client-side hash routing
- **Styling**: Custom CSS with responsive design

## 📊 Data Structure

The application uses a consolidated JSON file (`torrance_votes_smart_consolidated.json`) containing:

- **Meetings**: Meeting metadata, dates, video/agenda URLs
- **Votes**: Individual vote records with timestamps and results
- **Councilmembers**: Councilmember names and statistics
- **Summaries**: AI-generated meeting and councilmember summaries
- **Metadata**: Vote counts, meeting counts, etc.

## 🔧 Development

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/jstart/torrance-vote-viewer.git
   cd torrance-vote-viewer
   ```

2. Serve the files locally:
   ```bash
   # Using Python
   python3 -m http.server 8000

   # Using Node.js
   npx serve .

   # Using PHP
   php -S localhost:8000
   ```

3. Open your browser to `http://localhost:8000`

### File Organization

- **`index.html`**: Clean HTML structure with navigation and content area
- **`styles.css`**: All CSS styles including responsive design and utility classes
- **`app.js`**: Main application class with routing and data management
- **`utils.js`**: Utility functions for data processing and formatting
- **`templates.js`**: HTML template functions for consistent rendering

## 📈 Data Processing Scripts

### `merge_meta_ids.py`
Merges meta IDs from mapping files into vote data for precise video deep linking.

```bash
python3 merge_meta_ids.py
```

### `scrape_timestamps.py`
Scrapes actual video timestamps from Granicus player pages.

```bash
python3 scrape_timestamps.py
```

## 🎯 Key Features Explained

### Deep Linking
- **Video Links**: Direct links to specific timestamps in meeting videos
- **Agenda Links**: Links to specific agenda items in PDF agendas
- **Meta ID Integration**: Uses scraped meta IDs for precise video navigation

### Search Functionality
- **Text Search**: Search by agenda item or motion text
- **Filter by Councilmember**: Filter votes by specific councilmembers
- **Filter by Meeting**: Filter votes by specific meetings
- **Filter by Result**: Filter by passed/failed votes
- **Return Key Support**: Press Enter to search

### Responsive Design
- **Mobile-First**: Optimized for mobile devices
- **Flexible Layout**: Adapts to different screen sizes
- **Touch-Friendly**: Large buttons and touch targets

## 🔍 Navigation

The application uses client-side hash routing:

- `#/home` - Home page with statistics
- `#/meetings` - All meetings list
- `#/meeting/{id}` - Specific meeting details
- `#/councilmembers` - Councilmembers list
- `#/councilmember/{id}` - Specific councilmember details
- `#/year/{year}` - Meetings and votes for specific year
- `#/search` - Search interface

## 📱 Mobile Support

The application is fully responsive and includes:

- Mobile-optimized navigation
- Touch-friendly interface
- Responsive grid layouts
- Optimized typography for small screens
- Collapsible sections for better mobile UX

## 🚀 Deployment

The application is deployed on GitHub Pages:

1. Push changes to the `main` branch
2. GitHub Actions automatically deploys to `truman4congress.com/torrance-vote-viewer/`
3. Static hosting ensures fast loading and reliability

## 🔧 Configuration

### Data Sources
- **Primary Data**: `data/torrance_votes_smart_consolidated.json`
- **Meta ID Mapping**: `data/meta_id_mapping.json`
- **Video Timestamps**: `data/video_timestamps.json`

### Environment Variables
No environment variables required - the application runs entirely client-side.

## 📊 Performance

- **Static Files**: All assets are static for fast loading
- **Client-Side Processing**: No server-side processing required
- **Efficient Data Structure**: Optimized JSON structure for quick access
- **Lazy Loading**: Content loaded on demand

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is open source and available under the MIT License.

## 🆘 Support

For issues or questions:
1. Check the GitHub Issues page
2. Create a new issue with detailed description
3. Include browser console logs if applicable

## 🔄 Updates

The application is regularly updated with:
- New vote data
- Improved summaries
- Enhanced features
- Bug fixes
- Performance improvements

---

**Built with ❤️ for transparency in local government**
