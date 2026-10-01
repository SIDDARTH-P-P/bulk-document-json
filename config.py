"""
Configuration settings for FileToJSON API and Batch Engine.
"""

import os

# Server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))

# MongoDB settings
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "file_to_json")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "tracking_documents")

# Parallel worker threads (defaults to 16 for high-speed multi-core processing)
DEFAULT_WORKERS = min(32, (os.cpu_count() or 4) * 2)

# Max content length for uploads (500MB to allow 1000+ files in a single batch)
MAX_CONTENT_LENGTH = 500 * 1024 * 1024
