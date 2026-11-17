import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

PLACES_BASE_URL = "https://places.googleapis.com/v1"
DETAILS_FIELD_MASK = "id,displayName,formattedAddress,location,addressComponents"
CITY_COMPONENT_TYPES = (
    "locality",
    "postal_town",
    "administrative_area_level_2",
    "administrative_area_level_1",
)


def _api_key() -> str:
    key = settings.google_maps_server_api_key.get_secret_value()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places is not configured",
        )
    return key


async def _send(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        logger.warning("Google Places request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google Places is unavailable",
        ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    if response.status_code == status.HTTP_400_BAD_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Google Places rejected this request",
        )
    if response.status_code != status.HTTP_200_OK:
        logger.warning("Google Places returned HTTP %s", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google Places request failed",
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google Places returned an invalid response",
        ) from exc


async def autocomplete_places(
    client: httpx.AsyncClient,
    text: str,
    session_token: str | None,
    latitude: float | None,
    longitude: float | None,
) -> list[dict[str, str]]:
    body: dict[str, Any] = {"input": text}
    if session_token:
        body["sessionToken"] = session_token
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": 50000.0,
            }
        }

    data = await _send(
        client,
        "POST",
        f"{PLACES_BASE_URL}/places:autocomplete",
        headers={"X-Goog-Api-Key": _api_key()},
        json=body,
    )

    suggestions: list[dict[str, str]] = []
    for item in data.get("suggestions", []):
        prediction = item.get("placePrediction")
        if not prediction or not prediction.get("placeId"):
            continue

        formatted = prediction.get("structuredFormat", {})
        description = prediction.get("text", {}).get("text", "")
        suggestions.append(
            {
                "google_place_id": prediction["placeId"],
                "description": description,
                "main_text": formatted.get("mainText", {}).get("text", description),
                "secondary_text": formatted.get("secondaryText", {}).get("text", ""),
            }
        )
    return suggestions


def _component(components: list[dict[str, Any]], component_type: str) -> str | None:
    for component in components:
        if component_type in component.get("types", []):
            return component.get("longText")
    return None


async def get_place_details(
    client: httpx.AsyncClient,
    place_id: str,
    session_token: str | None = None,
) -> dict[str, Any]:
    params = {"sessionToken": session_token} if session_token else None
    data = await _send(
        client,
        "GET",
        f"{PLACES_BASE_URL}/places/{place_id}",
        headers={"X-Goog-Api-Key": _api_key(), "X-Goog-FieldMask": DETAILS_FIELD_MASK},
        params=params,
    )

    location = data.get("location") or {}
    if "latitude" not in location or "longitude" not in location or not data.get("id"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This place does not have usable coordinates",
        )

    components = data.get("addressComponents", [])
    city = next(
        (
            value
            for component_type in CITY_COMPONENT_TYPES
            if (value := _component(components, component_type))
        ),
        None,
    )
    country = _component(components, "country")
    address = data.get("formattedAddress") or ""

    return {
        "google_place_id": data["id"],
        "name": (data.get("displayName", {}).get("text") or address or "Unnamed venue")[:200],
        "address": address[:500],
        "city": city[:100] if city else None,
        "country": country[:100] if country else None,
        "latitude": float(location["latitude"]),
        "longitude": float(location["longitude"]),
    }