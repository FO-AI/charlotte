from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import setup_logging
from api.router import router  
import uvicorn
setup_logging(level='INFO')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - initializes clients once on startup"""
    print("Starting up Charlotte...")
    print("Charlotte startup complete!")
    yield
    print("Shutting down Charlotte...")


# Initialize FastAPI app
app = FastAPI(title="Charlotte",
              description="Charlotte is a chatbot that can answer questions about the UNC Charlotte campus and its resources.",
              version="1.0.0",
              lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the main API router
app.include_router(router)


if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["**/networkx/**"]
    )