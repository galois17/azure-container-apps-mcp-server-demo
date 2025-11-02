import asyncio
import logging
from typing import Any, Optional
import httpx
from fastmcp import FastMCP

logger = logging.getLogger("weather")

# Initialize FastMCP server
mcp = FastMCP("weather")

NWS_API_BASE = "https://api.weather.gov"
OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "weather-app/1.0"

async def make_request_with_retries(
    url: str,
    headers: Optional[dict[str, str]] = None,
    max_retries: int = 3,
    timeout: float = 15.0,
    backoff_factor: float = 1.5,
) -> Optional[dict[str, Any]]:
    """Make an async GET request with retries and exponential backoff."""
    headers = headers or {}
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    return data
                raise ValueError("Invalid response JSON structure.")
        except (httpx.RequestError, httpx.HTTPStatusError, asyncio.TimeoutError) as e:
            logger.warning(f"Attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(backoff_factor ** attempt)
        except Exception as e:
            logger.exception(f"Unexpected error in make_request_with_retries: {e}")
            break
    return None


async def make_nws_request(url: str) -> Optional[dict[str, Any]]:
    """Wrapper for NWS requests with proper headers."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    }
    return await make_request_with_retries(url, headers=headers)


def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""


@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state."""
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."
    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)


@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """
    Retrieve a concise weather forecast for a given geographic location.

    This function serves as the main MCP tool for weather retrieval. It first attempts
    to query the National Weather Service (NWS) API for a detailed, multi-period forecast.
    If the NWS API is unavailable or returns no data, the function automatically falls
    back to the Open-Meteo API to ensure a response is still provided.

    Args:
        latitude (float): The latitude of the location in decimal degrees.
        longitude (float): The longitude of the location in decimal degrees.

    Returns:
        str: A formatted, human-readable forecast summary. The output includes up to
        five forecast periods from NWS when available, or a current conditions summary
        from Open-Meteo if the fallback API is used.
    """
    try:
        # Primary: National Weather Service
        points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
        points_data = await make_nws_request(points_url)

        if points_data:
            forecast_url = points_data.get("properties", {}).get("forecast")
            if forecast_url:
                forecast_data = await make_nws_request(forecast_url)
                if forecast_data:
                    periods = forecast_data.get("properties", {}).get("periods", [])
                    if periods:
                        formatted = []
                        for p in periods[:5]:
                            name = p.get("name", "Unknown period")
                            temp = p.get("temperature")
                            unit = p.get("temperatureUnit", "")
                            wind = f"{p.get('windSpeed', '')} {p.get('windDirection', '')}".strip()
                            details = p.get("detailedForecast", "No details available.")
                            formatted.append(
                                f"{name}\nTemperature: {temp}°{unit}\nWind: {wind}\nForecast: {details}\n"
                            )

                        loc = points_data.get("properties", {}).get("relativeLocation", {})
                        city = loc.get("properties", {}).get("city", "")
                        state = loc.get("properties", {}).get("state", "")
                        header = f"Forecast for {city}, {state}".strip()
                        return f"{header}\n\n" + "\n---\n".join(formatted)

        # allback: Open-Meteo
        logger.warning("Falling back to Open-Meteo API...")
        open_meteo_url = (
            f"{OPEN_METEO_BASE}?latitude={latitude}&longitude={longitude}"
            "&current_weather=true"
        )
        data = await make_request_with_retries(open_meteo_url)
        if not data:
            return "Unable to fetch forecast from both NWS and Open-Meteo."

        current = data.get("current_weather", {})
        temp = current.get("temperature", "Unknown")
        windspeed = current.get("windspeed", "Unknown")
        winddir = current.get("winddirection", "Unknown")
        return (
            f"Open-Meteo fallback forecast:\n"
            f"Temperature: {temp}°C\n"
            f"Wind speed;: {windspeed} km/h\n"
            f"Wind direction: {winddir}°"
        )

    except Exception as e:
        import traceback
        tb = traceback.format_exc(limit=2)
        return f"Internal error fetching forecast: {e}\n\nTraceback:\n{tb}"


if __name__ == "__main__":
    mcp.run(transport="stdio")