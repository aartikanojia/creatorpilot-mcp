"""
YouTube Analytics API Client.

Provides OAuth-authenticated access to the YouTube Analytics API
using stored access tokens from the channels table.

Includes automatic token refresh when access tokens expire.
"""

import logging
from typing import Any, Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import config

logger = logging.getLogger(__name__)


class YouTubeAnalyticsClient:
    """
    YouTube Analytics API client using OAuth credentials.
    
    Uses stored access_token from the channels table to authenticate
    API requests. Automatically refreshes expired tokens using the
    refresh_token if available.
    """
    
    # YouTube Analytics API configuration
    API_SERVICE_NAME = "youtubeAnalytics"
    API_VERSION = "v2"
    
    # Google OAuth endpoints
    TOKEN_URI = "https://oauth2.googleapis.com/token"
    
    def __init__(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        on_token_refresh: Optional[callable] = None
    ) -> None:
        """
        Initialize the YouTube Analytics client.
        
        Args:
            access_token: OAuth access token from the channels table.
            refresh_token: OAuth refresh token for automatic token refresh.
            client_id: Google OAuth client ID (defaults to config).
            client_secret: Google OAuth client secret (defaults to config).
            on_token_refresh: Optional callback when token is refreshed.
                              Called with (new_access_token, new_refresh_token).
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id or getattr(config, 'google_client_id', None)
        self.client_secret = client_secret or getattr(config, 'google_client_secret', None)
        self.on_token_refresh = on_token_refresh
        self._service = None
        self._credentials = None
        logger.info("YouTubeAnalyticsClient initialized")
    
    def _build_credentials(self) -> Credentials:
        """
        Build Google OAuth credentials from access token.
        
        If the credentials are expired and a refresh_token is available,
        this method will automatically refresh the access token.
        
        Returns:
            Credentials object for API authentication.
        """
        if self._credentials is None:
            self._credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri=self.TOKEN_URI,
                client_id=self.client_id,
                client_secret=self.client_secret
            )
        
        # Check if credentials need refresh
        if self._credentials.expired and self._credentials.refresh_token:
            logger.info("Access token expired, attempting refresh...")
            try:
                self._credentials.refresh(Request())
                logger.info("Access token refreshed successfully")
                
                # Update stored access token
                self.access_token = self._credentials.token
                
                # Call the callback if provided (to persist the new token)
                if self.on_token_refresh:
                    self.on_token_refresh(
                        self._credentials.token,
                        self._credentials.refresh_token
                    )
            except Exception as e:
                logger.error(f"Failed to refresh access token: {e}")
                raise RuntimeError(
                    "Access token expired and refresh failed. "
                    "Please reconnect your YouTube channel."
                ) from e
        
        return self._credentials
    
    def _get_service(self) -> Any:
        """
        Get or create the YouTube Analytics API service.
        
        Returns:
            YouTube Analytics API service instance.
        """
        if self._service is None:
            credentials = self._build_credentials()
            self._service = build(
                self.API_SERVICE_NAME,
                self.API_VERSION,
                credentials=credentials,
                cache_discovery=False  # Required to avoid caching issues
            )
            logger.debug("YouTube Analytics API service built successfully")
        return self._service
    
    def query_reports(
        self,
        start_date: str,
        end_date: str,
        metrics: str,
        dimensions: Optional[str] = None,
        filters: Optional[str] = None,
        sort: Optional[str] = None,
        max_results: Optional[int] = None
    ) -> dict[str, Any]:
        """
        Query the YouTube Analytics reports API.
        
        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
            metrics: Comma-separated list of metrics to retrieve.
            dimensions: Optional comma-separated list of dimensions.
            filters: Optional filters for the query.
            sort: Optional sort order.
            
        Returns:
            Raw API response as dictionary.
            
        Raises:
            HttpError: If the API request fails.
        """
        service = self._get_service()
        
        # Build the query parameters
        query_params = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "metrics": metrics
        }
        
        if dimensions:
            query_params["dimensions"] = dimensions
        if filters:
            query_params["filters"] = filters
        if sort:
            query_params["sort"] = sort
        if max_results is not None:
            query_params["maxResults"] = max_results
        
        logger.info(
            f"Calling YouTube Analytics API: "
            f"metrics={metrics}, dimensions={dimensions}, "
            f"startDate={start_date}, endDate={end_date}"
        )
        
        try:
            response = service.reports().query(**query_params).execute()
            logger.debug(f"YouTube Analytics API response received: {len(response.get('rows', []))} rows")
            return response
        except HttpError as e:
            logger.error(f"YouTube Analytics API error: {e}")
            raise
