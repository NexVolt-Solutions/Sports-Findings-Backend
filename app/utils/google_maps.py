"""
Google Maps API integration for the Sports Platform.

Handles:
- Geocoding: Convert addresses to coordinates
- Places: Find nearby sports venues
- Directions: Calculate routes and distances
"""

import httpx
import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


class GoogleMapsAPIError(Exception):
    """Custom exception for Google Maps API errors."""
    pass


async def geocode_address(address: str) -> dict[str, float] | None:
    """
    Convert an address to latitude and longitude using Google Geocoding API.

    Args:
        address: The facility address to geocode.

    Returns:
        Dict with 'latitude' and 'longitude' keys, or None if lookup fails.

    Example:
        >>> coords = await geocode_address("Central Park, New York")
        >>> coords
        {'latitude': 40.785091, 'longitude': -73.968285}
    """
    if not settings.google_maps_api_key:
        logger.warning("Google Maps API key not configured")
        return None

    if not settings.geocoding_api_enabled:
        logger.debug("Geocoding API is disabled")
        return None

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": settings.google_maps_api_key
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Check if the request was successful
            if data.get("status") != "OK":
                logger.warning(f"Geocoding API error: {data.get('status')} - {data.get('error_message', 'Unknown error')}")
                return None

            # Extract coordinates from the first result
            if not data.get("results"):
                logger.warning(f"No geocoding results for address: {address}")
                return None

            location = data["results"][0]["geometry"]["location"]
            return {
                "latitude": location["lat"],
                "longitude": location["lng"]
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error during geocoding: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during geocoding: {e}")
        return None


async def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "sports_complex"
) -> list[dict] | None:
    """
    Find nearby places (stadiums, gyms, sports complexes) using Google Places API.

    Args:
        latitude: User's latitude.
        longitude: User's longitude.
        place_type: Type of place to search for. Default: "sports_complex".
                   Other options: "gym", "stadium", "park", etc.

    Returns:
        List of nearby places with name, coordinates, and distance.
        Returns None if API call fails.

    Example:
        >>> places = await find_nearby_places(40.7128, -74.0060, "gym")
        >>> places[0]
        {
            'name': 'Chelsea Piers',
            'latitude': 40.7505,
            'longitude': -74.0034,
            'address': '62 Chelsea Piers, New York, NY 10011',
            'distance_km': 0.89
        }
    """
    if not settings.google_maps_api_key:
        logger.warning("Google Maps API key not configured")
        return None

    if not settings.places_api_enabled:
        logger.debug("Places API is disabled")
        return None

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{latitude},{longitude}",
        "radius": settings.places_search_radius,  # Default 5km
        "type": place_type,
        "key": settings.google_maps_api_key
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK":
                logger.warning(f"Places API error: {data.get('status')} - {data.get('error_message', 'Unknown error')}")
                return None

            places = []
            for place in data.get("results", []):
                try:
                    distance = calculate_distance(
                        latitude, longitude,
                        place["geometry"]["location"]["lat"],
                        place["geometry"]["location"]["lng"]
                    )
                    places.append({
                        "name": place.get("name"),
                        "latitude": place["geometry"]["location"]["lat"],
                        "longitude": place["geometry"]["location"]["lng"],
                        "address": place.get("vicinity"),
                        "distance_km": round(distance, 2),
                        "rating": place.get("rating"),
                        "open_now": place.get("opening_hours", {}).get("open_now")
                    })
                except Exception as e:
                    logger.error(f"Error processing place data: {e}")
                    continue

            return places

    except httpx.HTTPError as e:
        logger.error(f"HTTP error during places search: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during places search: {e}")
        return None


async def get_directions(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    mode: str = "driving"
) -> dict | None:
    """
    Calculate route, distance, and travel time using Google Directions API.

    Args:
        origin_lat: Starting point latitude.
        origin_lng: Starting point longitude.
        destination_lat: Destination latitude.
        destination_lng: Destination longitude.
        mode: Travel mode ('driving', 'walking', 'transit'). Default: 'driving'.

    Returns:
        Dict with distance (km), duration (minutes), and polyline.
        Returns None if API call fails.

    Example:
        >>> directions = await get_directions(40.7128, -74.0060, 40.7580, -73.9855)
        >>> directions
        {
            'distance_km': 5.2,
            'duration_minutes': 18,
            'polyline': 'encoded_polyline_string',
            'steps': [...]
        }
    """
    if not settings.google_maps_api_key:
        logger.warning("Google Maps API key not configured")
        return None

    if not settings.directions_api_enabled:
        logger.debug("Directions API is disabled")
        return None

    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{destination_lat},{destination_lng}",
        "mode": mode or settings.directions_api_mode,
        "key": settings.google_maps_api_key
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK":
                logger.warning(f"Directions API error: {data.get('status')} - {data.get('error_message', 'Unknown error')}")
                return None

            if not data.get("routes"):
                logger.warning("No routes found")
                return None

            route = data["routes"][0]
            leg = route["legs"][0]

            return {
                "distance_km": leg["distance"]["value"] / 1000,  # Convert meters to km
                "duration_minutes": leg["duration"]["value"] // 60,  # Convert seconds to minutes
                "polyline": route.get("overview_polyline", {}).get("points"),
                "steps": leg.get("steps", [])
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error during directions lookup: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during directions lookup: {e}")
        return None


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.

    Args:
        lat1, lon1: First coordinate (latitude, longitude)
        lat2, lon2: Second coordinate (latitude, longitude)

    Returns:
        Distance in kilometers
    """
    from math import radians, sin, cos, sqrt, atan2

    # Earth's radius in kilometers
    R = 6371.0

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


async def validate_api_key() -> bool:
    """
    Validate the Google Maps API key by making a simple request.

    Returns:
        True if API key is valid, False otherwise.
    """
    if not settings.google_maps_api_key:
        logger.warning("Google Maps API key not configured")
        return False

    result = await geocode_address("New York")
    return result is not None
