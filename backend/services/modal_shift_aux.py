from pydantic import BaseModel
import requests
import asyncio


class Position(BaseModel):
    latitude: float
    longitude: float


def _get_route_sync(origin: Position, destination: Position, profile: str) -> dict:
    """
    Synchronous helper function to request OSRM route.
    Used by the async wrapper to avoid blocking.
    """
    url = (
        f"https://router.project-osrm.org/route/v1/{profile}/"
        f"{origin.longitude},{origin.latitude};"
        f"{destination.longitude},{destination.latitude}"
    )
    
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        
        if data.get('routes') and len(data['routes']) > 0:
            route = data['routes'][0]
            return {
                'distance': route['distance'],  # in meters
                'duration': route['duration'],  # in seconds
                'routes': data['routes']
            }
        else:
            raise Exception('No route found between origin and destination')
    else:
        raise Exception(f'OSRM request failed: {response.status_code}')


async def get_route_distance_and_duration(
    origin: Position,
    destination: Position,
    profile: str = "car"
) -> dict:
    """
    Request route information from OSRM (Open Source Routing Machine).
    Uses asyncio.to_thread to run blocking requests without blocking the event loop.
    
    Parameters:
        - origin: Position object with latitude and longitude
        - destination: Position object with latitude and longitude
        - profile: Routing profile ('car', 'bike', 'foot'). Defaults to 'car'
    
    Returns:
        Dictionary containing:
        - distance: Distance in meters
        - duration: Duration in seconds
        - routes: Full OSRM response routes data
    
    Raises:
        Exception if the request fails
    """
    try:
        result = await asyncio.to_thread(_get_route_sync, origin, destination, profile)
        return result
    except Exception as e:
        raise Exception(f'Error requesting OSRM route: {str(e)}')
