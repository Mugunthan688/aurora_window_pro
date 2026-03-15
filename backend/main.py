"""
AuroraWindow Pro — Backend Entry Point
FastAPI application for real-time aurora forecasting and visualization.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.space_weather_api import router as space_weather_router
from api.visibility_api import router as visibility_router
from api.routing_api import router as routing_router
from api.alert_api import router as alert_router

# ─── App Initialization ───────────────────────────────────────────────────────

app = FastAPI(
    title="AuroraWindow Pro",
    description=(
        "Real-time aurora forecasting and visualization platform. "
        "Provides space weather data, hyper-local visibility scoring, "
        "aurora chaser routing, and substorm alert intelligence."
    ),
    version="1.0.0",
)

# ─── CORS Middleware ──────────────────────────────────────────────────────────
# Allows the React frontend (localhost:5173 via Vite) to call this backend.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # fallback CRA dev server
        "*",                       # open for hackathon deployment
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────

app.include_router(space_weather_router, prefix="/api", tags=["Space Weather"])
app.include_router(visibility_router,    prefix="/api", tags=["Visibility"])
app.include_router(routing_router,       prefix="/api", tags=["Routing"])
app.include_router(alert_router,         prefix="/api", tags=["Alerts"])

# ─── Core Endpoints ───────────────────────────────────────────────────────────

@app.get("/", tags=["Root"])
def root():
    """Root endpoint — confirms the API is live."""
    return {
        "project": "AuroraWindow Pro",
        "status":  "running",
        "message": "The aurora app that sees through mountains.",
    }


@app.get("/health", tags=["Root"])
def health():
    """Health check endpoint — used by Railway / deployment monitors."""
    return {
        "status": "healthy",
    }


# ─── Run ─────────────────────────────────────────────────────────────────────
# Run with: uvicorn main:app --reload

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)