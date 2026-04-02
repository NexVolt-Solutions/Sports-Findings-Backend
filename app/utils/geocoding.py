import httpx
import logging
import math
from dataclasses import dataclass
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

GEOCODING_URL    = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_AC_URL    = "https://maps.googleapis.com/maps/api/place/autocomplete/json"

# Earth radius in km
EARTH_RADIUS_KM = 6371.0


@dataclass
class GeocodingResult:
    latitude: float
    longitude: float
    formatted_address: str


@dataclass
class BoundingBox:
    """A lat/lng bounding box used for fast spatial pre-filtering."""
    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float


async def geocode_address(address: str) -> Optional[GeocodingResult]:
    """
    Convert a text address into GPS coordinates using Google Maps Geocoding API.

    Returns a GeocodingResult on success, or None if geocoding fails.
    Never raises — failures are logged so match creation is never blocked.

    Args:
        address: Raw address entered by the user
                 e.g. "Nørrebrogade 285, 2200 Nørrebro"

    Returns:
        GeocodingResult(latitude, longitude, formatted_address) or None
    """
    if not settings.google_maps_api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not configured — skipping geocoding")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GEOCODING_URL,
                params={
                    "address": address,
                    "key":     settings.google_maps_api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning(f"Geocoding no results for: {address!r} (status={data.get('status')})")
            return None

        result   = data["results"][0]
        location = result["geometry"]["location"]

        return GeocodingResult(
            latitude=location["lat"],
            longitude=location["lng"],
            formatted_address=result.get("formatted_address", address),
        )

    except httpx.HTTPError as e:
        logger.error(f"Geocoding HTTP error for {address!r}: {e}")
        return None
    except Exception as e:
        logger.error(f"Geocoding unexpected error for {address!r}: {e}")
        return None


def haversine_distance_km(
    lat1: float, lng1: float,
    lat2: float, lng2: float,
) -> float:
    """
    Calculate the great-circle distance between two points on Earth
    using the Haversine formula.

    Args:
        lat1, lng1: Coordinates of the first point (user location)
        lat2, lng2: Coordinates of the second point (match location)

    Returns:
        Distance in kilometres, rounded to 2 decimal places.
    """
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    # Clamp to [0, 1] to prevent floating-point domain errors in asin
    c = 2 * math.asin(math.sqrt(min(1.0, a)))
    return round(EARTH_RADIUS_KM * c, 2)


def build_bounding_box(lat: float, lng: float, radius_km: float) -> BoundingBox:
    """
    Calculate a lat/lng bounding box around a point for a given radius.

    Used as a fast pre-filter (index scan) before the expensive Haversine
    calculation. The box is slightly larger than the actual radius circle.

    Args:
        lat:       Center latitude
        lng:       Center longitude
        radius_km: Search radius in km

    Returns:
        BoundingBox with lat_min, lat_max, lng_min, lng_max
    """
    # 1 degree latitude ≈ 111.0 km (constant)
    lat_delta = radius_km / 111.0

    # 1 degree longitude varies by latitude
    # Avoid division by zero near poles with small epsilon
    lng_delta = radius_km / (111.0 * math.cos(math.radians(lat)) + 1e-9)

    return BoundingBox(
        lat_min=lat - lat_delta,
        lat_max=lat + lat_delta,
        lng_min=lng - lng_delta,
        lng_max=lng + lng_delta,
    )


def is_within_radius(
    user_lat: float, user_lng: float,
    match_lat: float, match_lng: float,
    radius_km: float,
) -> tuple[bool, float]:
    """
    Check if a match location is within the given radius of the user.

    Returns:
        (is_within: bool, distance_km: float)
    """
    distance = haversine_distance_km(user_lat, user_lng, match_lat, match_lng)
    return distance <= radius_km, distance
