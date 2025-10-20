# Bulletproof Import Script Configuration
# =====================================

# API Configuration
GEMINI_API_KEY = "your_gemini_api_key_here"  # Get from https://makersuite.google.com/app/apikey

# Import Settings
DEFAULT_OUTPUT_FILE = "data/torrance_votes_smart_consolidated.json"
DEFAULT_BACKUP_DIR = "data/backups"
DEFAULT_LOG_DIR = "logs"

# Scraping Settings
MAX_RETRIES = 3
RETRY_DELAY = 1.0
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 0.5  # Delay between requests to avoid rate limiting

# Deduplication Settings
CONSOLIDATION_THRESHOLD = 0.8  # Minimum confidence score for vote consolidation
FRAME_NUMBER_TOLERANCE = 5     # Maximum frame number difference for consolidation

# Validation Settings
REQUIRED_VOTE_FIELDS = ['meeting_id', 'agenda_item', 'individual_votes']
REQUIRED_MEETING_FIELDS = ['title', 'date', 'video_url']

# Logging Settings
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_FILE = "import_log.txt"

# Summary Generation Settings
SUMMARY_MAX_VOTES = 50  # Maximum votes to include in summary
SUMMARY_LANGUAGE = "en"  # Language for summaries
SUMMARY_STYLE = "professional"  # professional, casual, technical
