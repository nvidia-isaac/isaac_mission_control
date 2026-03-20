import os
import logging
import argparse
import uvicorn
import yaml
import httpx
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional, Dict, Any
from pydantic.v1 import BaseModel, Field
import shutil
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import json


class Point(BaseModel):
    """ 2D Point """
    x: float = Field(title="X coordinate of a point")
    y: float = Field(title="Y coordinate of a point")

# Additional models for route visualization
class MissionData(BaseModel):
    """Simplified MissionData model to match what mission_control_api expects"""
    route: List[Point]
    solver: Optional[str] = "CPU_DIJKSTRA"  # Default solver
    timeout: Optional[int] = 60

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("waypoint-selection-ui")

# Create directories for uploads
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAP_DIR = UPLOAD_DIR / "maps"
MAP_DIR.mkdir(exist_ok=True)
CONFIG_DIR = UPLOAD_DIR / "configs"
CONFIG_DIR.mkdir(exist_ok=True)


class GeneratePathRequest(BaseModel):
    points: List[Point]  # Using the Point class defined above
    resolution: float
    origin: List[float]

class MapConfig(BaseModel):
    image: str
    resolution: float
    origin: List[float]
    negate: Optional[int] = 0
    occupied_thresh: Optional[float] = 0.65
    free_thresh: Optional[float] = 0.196

# Create FastAPI app
app = FastAPI(title="Waypoint Selection UI Service")

# Add CORS middleware to allow loading from external sources
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up templates
templates = Jinja2Templates(directory="waypoint_selection_ui/templates")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Serve the main UI page
    """
    # List available maps and configs
    map_files = [f.name for f in MAP_DIR.glob("*.png") if f.is_file()]
    config_files = [f.name for f in CONFIG_DIR.glob("*.yaml") if f.is_file()]
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "map_files": map_files,
            "config_files": config_files
        }
    )

@app.post("/upload/map")
async def upload_map(map_file: UploadFile = File(...)):
    """
    Upload a map image file
    """
    if not map_file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    file_extension = map_file.filename.split(".")[-1].lower()
    if file_extension not in ["png", "jpg", "jpeg"]:
        raise HTTPException(status_code=400, detail="Only PNG and JPG files are supported")
    
    file_location = MAP_DIR / map_file.filename
    with open(file_location, "wb") as file_object:
        shutil.copyfileobj(map_file.file, file_object)
    
    logger.info(f"Uploaded map file to {file_location}")
    return {"filename": map_file.filename}

@app.post("/upload/config")
async def upload_config(config_file: UploadFile = File(...)):
    """
    Upload a map YAML config file
    """
    if not config_file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    file_extension = config_file.filename.split(".")[-1].lower()
    if file_extension not in ["yaml", "yml"]:
        raise HTTPException(status_code=400, detail="Only YAML files are supported")
    
    file_location = CONFIG_DIR / config_file.filename
    with open(file_location, "wb") as file_object:
        shutil.copyfileobj(config_file.file, file_object)
    
    # Validate the YAML file contains required fields
    try:
        with open(file_location, "r") as f:
            config_data = yaml.safe_load(f)
            MapConfig(**config_data)  # Validate with pydantic model
    except Exception as e:
        # Remove invalid file
        os.remove(file_location)
        raise HTTPException(status_code=400, detail=f"Invalid config file: {str(e)}")
    
    logger.info(f"Uploaded config file to {file_location}")
    return {"filename": config_file.filename}

@app.get("/map/{map_filename}")
async def get_map(map_filename: str):
    """
    Serve a map file
    """
    file_path = MAP_DIR / map_filename
    logger.info(f"Attempting to serve map file from: {file_path}")
    
    if not file_path.exists():
        logger.error(f"Map file not found: {file_path}")
        raise HTTPException(status_code=404, detail=f"Map file not found: {map_filename}")
    
    logger.info(f"Serving map file: {file_path}")
    return FileResponse(file_path)

@app.get("/config/{config_filename}")
async def get_config(config_filename: str):
    """
    Get a config file
    """
    file_path = CONFIG_DIR / config_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Config file not found")
    
    try:
        with open(file_path, "r") as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading config file: {str(e)}")
    
    return config_data

@app.post("/generate-waypoints")
async def generate_waypoints(request: GeneratePathRequest):
    """
    Generate waypoints from selected points on the map
    """
    if len(request.points) < 2:
        raise HTTPException(status_code=400, detail="At least 2 points are required")
    points = request.points
    logger.info(f"Generating waypoints from {len(points)} selected points")
    return points

@app.get("/health")
async def health():
    """
    Health check endpoint
    """
    return {"status": "ok"}

# Add new endpoint for route visualization
@app.post("/visualize-route", response_class=Response)
async def visualize_route(points: List[Point]):
    """
    Call the mission control API to visualize a route
    
    Args:
        points: List of waypoints to visualize
        
    Returns:
        PNG image with the route visualized on the map or a JSON error message
    """
    if len(points) < 2:
        raise HTTPException(status_code=400, detail="At least 2 points are required for route visualization")
    
    logger.info(f"Visualizing route with {len(points)} waypoints")
    
    # Create the mission data object
    mission_data = MissionData(route=points)
    
    # Get the mission control API URL from environment or use default
    mc_api_url = os.environ.get("MISSION_CONTROL_API_URL", "http://localhost:8050/api/v1")
    endpoint = f"{mc_api_url}/visualize_route"
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:  # Shorter timeout to fail faster
            response = await client.post(
                endpoint, 
                json=mission_data.dict(),
                headers={"Accept": "image/png"}
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to visualize route: {response.text}")
                return Response(
                    content=json.dumps({
                        "success": False,
                        "message": "Mission Control service responded with an error. Please check the logs."
                    }),
                    media_type="application/json"
                )
            
            # Return the image directly
            return Response(content=response.content, media_type="image/png")
            
    except httpx.ConnectError:
        logger.error("Cannot connect to Mission Control service")
        return Response(
            content=json.dumps({
                "success": False,
                "message": "Cannot connect to Mission Control service. Please ensure Mission Control is running."
            }),
            media_type="application/json"
        )
    except httpx.TimeoutException:
        logger.error("Connection to Mission Control service timed out")
        return Response(
            content=json.dumps({
                "success": False, 
                "message": "Connection to Mission Control service timed out. Please try again later."
            }),
            media_type="application/json"
        )
    except Exception as e:
        logger.error(f"Error visualizing route: {str(e)}")
        return Response(
            content=json.dumps({
                "success": False,
                "message": f"Error visualizing route: {str(e)}"
            }),
            media_type="application/json"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Waypoint Selection UI Service")
    parser.add_argument("--host", type=str, default="localhost", help="Service host")
    parser.add_argument("--port", type=int, default=8051, help="Service port")
    args = parser.parse_args()
    
    logger.info(f"Starting Waypoint Selection UI Service on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port) 