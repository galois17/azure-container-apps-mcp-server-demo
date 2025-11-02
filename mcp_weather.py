import asyncio
import logging
from typing import Any, Optional
import httpx
from fastmcp import FastMCP

logger = logging.getLogger("weather")

# Initialize FastMCP server
mcp = FastMCP("weather")

NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

async def make_nws_request(
    url: str,
    max_retries: int = 3,
    timeout: float = 15.0,
    backoff_factor: float = 1.5,
) -> Optional[dict[str, Any]]:
    """
    Make an async GET request to the NWS API with retries and backoff.

    Args:
        url: Full NWS API URL (e.g. "https://api.weather.gov/points/42.36,-71.06")
        max_retries: Maximum number of retry attempts for transient errors.
        timeout: Per-request timeout in seconds.
        backoff_factor: Multiplier for exponential backoff between retries.

    Returns:
        Parsed JSON response if successful, else None.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    }

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                try:
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("Invalid response format (expected JSON object).")
                    return data
                except Exception as parse_error:
                    logger.warning(f"Failed to parse NWS response JSON: {parse_error}")
                    return None

        except httpx.RequestError as e:
            # Network issues (DNS, connection timeout, etc.)
            logger.warning(f"Network error contacting NWS: {e}")
        except httpx.HTTPStatusError as e:
            # Handle common HTTP status codes
            status = e.response.status_code
            if status in (429, 500, 502, 503, 504):
                logger.warning(f"NWS transient error (status {status}), retrying...")
            else:
                logger.error(f"NWS API returned error {status}: {e.response.text[:200]}")
                return None
        except asyncio.TimeoutError:
            logger.warning("NWS request timed out.")
        except Exception as e:
            logger.exception(f"Unexpected error fetching NWS data: {e}")
            return None

        # Wait before retrying (exponential backoff)
        await asyncio.sleep(backoff_factor ** attempt)

    logger.error(f"Exceeded max retries ({max_retries}) for NWS URL: {url}")
    return None

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
    """
    Get weather alerts for a US state.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
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
    Get a concise 5-period forecast for a given latitude and longitude
    using the National Weather Service API.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location

    Returns:
        A formatted multiline string of forecast data, or an explanatory
        message if no forecast could be retrieved.
    """
    try:
        # Query the NWS
        points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
        points_data = await make_nws_request(points_url)

        if not points_data:
            return f"Unable to fetch forecast grid point for ({latitude:.2f}, {longitude:.2f})."

        forecast_url = (
            points_data.get("properties", {}).get("forecast")
        )
        if not forecast_url:
            office = points_data.get("properties", {}).get("cwa", "Unknown office")
            return f"Forecast URL missing in NWS response. (Reporting office: {office})"

        # Request the forecast
        forecast_data = await make_nws_request(forecast_url)
        if not forecast_data:
            return "Unable to fetch detailed forecast."

        periods = (
            forecast_data.get("properties", {}).get("periods", [])
        )
        if not periods:
            return "Forecast data is empty or malformed."

        # Step 3: Format up to 5 periods into a readable summary
        formatted = []
        for p in periods[:5]:
            name = p.get("name", "Unknown period")
            temp = p.get("temperature")
            unit = p.get("temperatureUnit", "")
            wind = f"{p.get('windSpeed', '')} {p.get('windDirection', '')}".strip()
            details = p.get("detailedForecast", "No details available.")

            section = (
                f"🌤 **{name}**\n"
                f"• Temperature: {temp}°{unit}\n"
                f"• Wind: {wind}\n"
                f"• Forecast: {details}"
            )
            formatted.append(section.strip())

        location = points_data.get("properties", {}).get("relativeLocation", {})
        city = location.get("properties", {}).get("city", "")
        state = location.get("properties", {}).get("state", "")

        header = f"📍 Forecast for {city}, {state}".strip()
        return f"{header}\n\n" + "\n\n---\n\n".join(formatted)

    except Exception as e:
        import traceback
        tb = traceback.format_exc(limit=2)
        return f"Internal error fetching forecast: {e}\n\nTraceback:\n{tb}"

if __name__ == "__main__":
    # Initialize and run
    mcp.run(transport='stdio')