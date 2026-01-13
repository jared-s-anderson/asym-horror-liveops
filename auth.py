from fastapi import Header, HTTPException
import os

INGEST_API_KEY = os.getenv("INGEST_API_KEY")

def require_api_key(x_api_key: str = Header(...)):
    if x_api_key != INGEST_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )