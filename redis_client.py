import os
import redis

# This gets the Redis URL from the environment variables and there is a fallback to localhost for local development.
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

# This creates the Redis client.
redis_client = redis.from_url(REDIS_URL)