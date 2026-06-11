import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import lectures, chat, content

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Academic Assistant API",
    description="Backend API for processing lecture recordings and providing AI-powered Q&A",
    version="0.1.0"
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(lectures.router)
app.include_router(chat.router)
app.include_router(content.router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "AI Academic Assistant API is running"
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "service": "academic-assistant-backend",
        "version": "0.1.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
