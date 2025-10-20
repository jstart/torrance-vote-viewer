# Torrance Vote Viewer - Static Deployment

This is a static web application that can be deployed to any static hosting service.

## 🚀 Deployment Options

### Option 1: GitHub Pages (Recommended)

1. **Create a GitHub repository**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/torrance-vote-viewer.git
   git push -u origin main
   ```

2. **Enable GitHub Pages**
   - Go to repository Settings → Pages
   - Source: Deploy from a branch
   - Branch: main
   - Folder: / (root)
   - Save

3. **Your site will be available at:**
   `https://YOUR_USERNAME.github.io/torrance-vote-viewer`

### Option 2: Netlify

1. **Drag and drop deployment**
   - Go to [netlify.com](https://netlify.com)
   - Drag the `static-deploy` folder to the deploy area
   - Your site will be live instantly

2. **Git-based deployment**
   - Connect your GitHub repository to Netlify
   - Build command: (leave empty)
   - Publish directory: `/` (root)

### Option 3: Vercel

1. **Install Vercel CLI**
   ```bash
   npm i -g vercel
   ```

2. **Deploy**
   ```bash
   cd static-deploy
   vercel
   ```

### Option 4: Surge.sh

1. **Install Surge**
   ```bash
   npm install -g surge
   ```

2. **Deploy**
   ```bash
   cd static-deploy
   surge
   ```

## 📁 Required Files

The static deployment only needs these files:
- `index.html` - Main application
- `data/torrance_votes_consolidated_final.json` - Vote data
- `data/` directory with all JSON files

## 🔧 Configuration

The application automatically detects the environment and adjusts paths accordingly:
- **Local development**: Uses relative paths
- **Static hosting**: Uses absolute paths for data files

## 🌐 Features

✅ **Client-side routing** - Hash-based navigation works without server  
✅ **Static data loading** - JSON files served as static assets  
✅ **Search functionality** - Pure JavaScript filtering  
✅ **Deep linking** - Direct links to video chapters and agenda items  
✅ **Responsive design** - Works on all devices  

## 📊 Data Structure

The application loads data from:
- `data/torrance_votes_consolidated_final.json` - Main vote data
- All other JSON files in the `data/` directory

## 🔗 Deep Linking

The application generates deep links to:
- **Video chapters**: `https://torrance.granicus.com/MediaPlayer.php?view_id=8&clip_id=MEETING_ID&meta_id=META_ID`
- **Agenda items**: `https://torrance.granicus.com/GeneratedAgendaViewer.php?view_id=8&clip_id=MEETING_ID`

## 🎯 Routes Supported

- `/` - Home page
- `/#/meetings` - All meetings
- `/#/meeting/MEETING_ID` - Specific meeting
- `/#/councilmembers` - All councilmembers
- `/#/councilmember/COUNCILMEMBER_ID` - Specific councilmember
- `/#/year/2025` - Year view
- `/#/search` - Search interface

## 🚀 Quick Start

1. Copy files from `static-deploy/` to your hosting service
2. Ensure `data/` directory is included
3. Access your site - routing will work automatically!

## 📝 Notes

- No server-side code required
- All functionality is client-side JavaScript
- CORS is not an issue since data is served from same domain
- Hash routing works on all static hosts
- Search and filtering are instant (no API calls needed)
