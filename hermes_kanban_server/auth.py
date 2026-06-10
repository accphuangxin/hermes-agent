"""Authentication middleware for Kanban API Server"""

import hmac
import hashlib
from typing import Optional
from aiohttp import web


def create_auth_middleware(api_key: Optional[str]):
    """
    Create authentication middleware for Bearer token validation.

    Uses HMAC SHA256 constant-time comparison to prevent timing attacks.

    Args:
        api_key: Optional API key. If None, authentication is disabled.

    Returns:
        aiohttp middleware function
    """
    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        # Skip auth for health check or if no API key configured
        if request.path == "/v1/health" or not api_key:
            return await handler(request)

        # Extract Bearer token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response(
                {"error": "Missing or invalid Authorization header"},
                status=401
            )

        token = auth_header[7:].strip()  # Remove "Bearer " prefix

        # Constant-time comparison to prevent timing attacks
        expected_digest = hashlib.sha256(api_key.encode()).digest()
        provided_digest = hashlib.sha256(token.encode()).digest()

        if not hmac.compare_digest(expected_digest, provided_digest):
            return web.json_response(
                {"error": "Unauthorized"},
                status=401
            )

        return await handler(request)

    return auth_middleware


def check_auth(request: web.Request, api_key: Optional[str]) -> Optional[web.Response]:
    """
    Check authentication for a single request (for use outside middleware).

    Args:
        request: aiohttp request object
        api_key: Optional API key

    Returns:
        401 error response if auth fails, None if auth succeeds
    """
    if not api_key:
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return web.json_response(
            {"error": "Missing or invalid Authorization header"},
            status=401
        )

    token = auth_header[7:].strip()

    expected_digest = hashlib.sha256(api_key.encode()).digest()
    provided_digest = hashlib.sha256(token.encode()).digest()

    if not hmac.compare_digest(expected_digest, provided_digest):
        return web.json_response({"error": "Unauthorized"}, status=401)

    return None
