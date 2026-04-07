"""
Places and location discovery endpoints.

Allows users to:
- Discover nearby sports venues
- Get directions to matches
- Find sports facilities in their area
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import logging

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.utils.google_maps import (
    find_nearby_places,
    get_directions,
    geocode_address,
    validate_api_key
)
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/places", tags=["Places & Locations"])


# ─── Response Models ──────────────────────────────────────────────────────────
class NearbyPlace(BaseModel):
    """A nearby sports facility or location."""
    name: str
    latitude: float
    longitude: float
    address: str | None = None
    distance_km: float
    rating: float | None = None
    open_now: bool | None = None


class NearbyPlacesResponse(BaseModel):
    """Response for nearby places search."""
    places: list[NearbyPlace]
    count: int
    latitude: float
    longitude: float
    search_radius_km: int


class DirectionsInfo(BaseModel):
    """Route information between two points."""
    distance_km: float
    duration_minutes: int
    polyline: str | None = None


class APIKeyValidationResponse(BaseModel):
    """Response for API key validation."""
    is_valid: bool
    message: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/nearby",
    response_model=NearbyPlacesResponse,
    summary="Find nearby sports venues",
    description="Find nearby sports facilities (gyms, stadiums, courts) based on user's location."
)
async def get_nearby_places(
    latitude: float = Query(..., description="User's latitude"),
    longitude: float = Query(..., description="User's longitude"),
    place_type: str = Query("sports_complex", description="Type of venue: sports_complex, gym, stadium, park"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Discover nearby sports venues.

    Query Parameters:
    - latitude: User's current latitude
    - longitude: User's current longitude
    - place_type: Type of venue to search (sports_complex, gym, stadium, park, etc.)

    Returns:
    - List of nearby places with distance and ratings
    """
    logger.info(f"User {current_user.id} searching for nearby {place_type} venues at ({latitude}, {longitude})")

    places = await find_nearby_places(latitude, longitude, place_type)

    if places is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve nearby places. Google Maps API may be unavailable."
        )

    return NearbyPlacesResponse(
        places=places,
        count=len(places),
        latitude=latitude,
        longitude=longitude,
        search_radius_km=5
    )


@router.get(
    "/directions",
    response_model=DirectionsInfo,
    summary="Get directions to a location",
    description="Calculate route, distance, and travel time from user's location to a match venue."
)
async def get_route_directions(
    origin_lat: float = Query(..., description="Starting latitude"),
    origin_lng: float = Query(..., description="Starting longitude"),
    destination_lat: float = Query(..., description="Destination latitude"),
    destination_lng: float = Query(..., description="Destination longitude"),
    mode: str = Query("driving", description="Travel mode: driving, walking, transit"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get directions and travel information to a match.

    Query Parameters:
    - origin_lat, origin_lng: Starting location
    - destination_lat, destination_lng: Match venue location
    - mode: Travel mode (driving, walking, transit)

    Returns:
    - Distance in kilometers
    - Travel time in minutes
    - Polyline for map rendering (frontend)
    """
    logger.info(f"User {current_user.id} requesting directions from ({origin_lat}, {origin_lng}) to ({destination_lat}, {destination_lng})")

    directions = await get_directions(origin_lat, origin_lng, destination_lat, destination_lng, mode)

    if directions is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to calculate directions. Google Maps API may be unavailable."
        )

    return directions


@router.get(
    "/geocode",
    response_model=dict,
    summary="Geocode an address",
    description="Convert a facility address to latitude and longitude coordinates."
)
async def geocode(
    address: str = Query(..., description="Address to geocode"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Convert an address to coordinates.

    Query Parameters:
    - address: The facility address to convert

    Returns:
    - latitude and longitude
    """
    logger.info(f"User {current_user.id} geocoding address: {address}")

    coords = await geocode_address(address)

    if coords is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to geocode the address. Google Maps API may be unavailable or address is invalid."
        )

    return coords


@router.get(
    "/health",
    response_model=APIKeyValidationResponse,
    summary="Validate Google Maps API",
    description="Check if Google Maps API integration is properly configured and working."
)
async def check_maps_health():
    """
    Validate Google Maps API configuration.

    Returns:
    - is_valid: Whether the API key is working
    - message: Status message
    """
    is_valid = await validate_api_key()

    return APIKeyValidationResponse(
        is_valid=is_valid,
        message="Google Maps API is working correctly" if is_valid else "Google Maps API is not configured or key is invalid"
    )
