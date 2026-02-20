"""
Unit tests for the MCP Server (server.py).

Tests cover:
- Health check endpoint
- Execute endpoint (success and error cases)
- Root endpoint
- CORS configuration
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from server import app
from registry.schemas import ExecuteResponse


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Synchronous test client for simple endpoint tests."""
    return TestClient(app)


@pytest.fixture
def mock_execute_response():
    """Create a mock ExecuteResponse for testing."""
    return ExecuteResponse(
        success=True,
        content="Test response content",
        content_type="text",
        tools_used=["fetch_analytics"],
        tool_outputs={"data": {"views": 100}},
        metadata={"intent": "analytics", "confidence": 0.9},
        error=None
    )


# =============================================================================
# Health Check Endpoint Tests
# =============================================================================

class TestHealthCheck:
    """Tests for the /health endpoint."""

    def test_health_check_returns_200(self, client):
        """Test that health check returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_returns_healthy_status(self, client):
        """Test that health check returns healthy status."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_check_returns_version(self, client):
        """Test that health check returns API version."""
        response = client.get("/health")
        data = response.json()
        assert data["version"] == "1.0.0"

    def test_health_check_returns_llm_provider(self, client):
        """Test that health check returns configured LLM provider."""
        response = client.get("/health")
        data = response.json()
        assert "llm_provider" in data

    def test_health_check_response_schema(self, client):
        """Test that health check response matches expected schema."""
        response = client.get("/health")
        data = response.json()

        # Verify all required fields are present
        assert "status" in data
        assert "version" in data
        assert "llm_provider" in data

        # Verify types
        assert isinstance(data["status"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["llm_provider"], str)


# =============================================================================
# Root Endpoint Tests
# =============================================================================

class TestRootEndpoint:
    """Tests for the / root endpoint."""

    def test_root_returns_200(self, client):
        """Test that root endpoint returns 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_service_info(self, client):
        """Test that root endpoint returns service information."""
        response = client.get("/")
        data = response.json()

        assert data["service"] == "CreatorPilot MCP Server"
        assert data["version"] == "1.0.0"

    def test_root_contains_docs_info(self, client):
        """Test that root endpoint contains docs information."""
        response = client.get("/")
        data = response.json()

        assert "docs" in data


# =============================================================================
# Execute Endpoint Tests
# =============================================================================

class TestExecuteEndpoint:
    """Tests for the /execute endpoint."""

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_execute_response):
        """Test successful execution request."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_execute_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics"
                    }
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["content"] == "Test response content"

    @pytest.mark.asyncio
    async def test_execute_with_metadata(self, mock_execute_response):
        """Test execution request with metadata."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_execute_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics",
                        "metadata": {"user_plan": "pro", "timezone": "UTC"}
                    }
                )

            assert response.status_code == 200
            mock_execute.assert_called_once()
            call_kwargs = mock_execute.call_args.kwargs
            assert call_kwargs["metadata"] == {
                "user_plan": "pro", "timezone": "UTC"}

    @pytest.mark.asyncio
    async def test_execute_validates_user_id(self):
        """Test that execute validates user_id is present."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                json={
                    "channel_id": "channel_456",
                    "message": "Show me analytics"
                }
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_execute_validates_channel_id(self):
        """Test that execute validates channel_id is present."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                json={
                    "user_id": "user_123",
                    "message": "Show me analytics"
                }
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_execute_validates_message(self):
        """Test that execute validates message is present."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                json={
                    "user_id": "user_123",
                    "channel_id": "channel_456"
                }
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_execute_validates_empty_user_id(self):
        """Test that execute rejects empty user_id."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                json={
                    "user_id": "",
                    "channel_id": "channel_456",
                    "message": "Show me analytics"
                }
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_execute_validates_empty_message(self):
        """Test that execute rejects empty message."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                json={
                    "user_id": "user_123",
                    "channel_id": "channel_456",
                    "message": ""
                }
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_execute_handles_value_error(self):
        """Test that execute returns 400 for ValueError."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = ValueError("Invalid input parameter")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics"
                    }
                )

            assert response.status_code == 400
            assert "Invalid input parameter" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_execute_handles_permission_error(self):
        """Test that execute returns 403 for PermissionError."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = PermissionError(
                "Access denied for this plan")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics"
                    }
                )

            assert response.status_code == 403
            assert "Access denied" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_execute_handles_unexpected_error(self):
        """Test that execute returns 500 for unexpected errors."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = RuntimeError(
                "Unexpected internal error")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics"
                    }
                )

            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_execute_returns_tools_used(self, mock_execute_response):
        """Test that execute response includes tools_used."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_execute_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics"
                    }
                )

            data = response.json()
            assert "tools_used" in data
            assert data["tools_used"] == ["fetch_analytics"]

    @pytest.mark.asyncio
    async def test_execute_returns_tool_outputs(self, mock_execute_response):
        """Test that execute response includes tool_outputs."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_execute_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics"
                    }
                )

            data = response.json()
            assert "tool_outputs" in data
            assert data["tool_outputs"] == {"data": {"views": 100}}

    @pytest.mark.asyncio
    async def test_execute_returns_metadata(self, mock_execute_response):
        """Test that execute response includes metadata."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_execute_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show me analytics"
                    }
                )

            data = response.json()
            assert "metadata" in data
            assert data["metadata"]["intent"] == "analytics"

    @pytest.mark.asyncio
    async def test_execute_passes_correct_arguments(self, mock_execute_response):
        """Test that execute passes correct arguments to execute_context_request."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_execute_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_abc",
                        "channel_id": "channel_xyz",
                        "message": "Test message",
                        "metadata": {"key": "value"}
                    }
                )

            mock_execute.assert_called_once_with(
                user_id="user_abc",
                channel_id="channel_xyz",
                message="Test message",
                metadata={"key": "value"}
            )


# =============================================================================
# CORS Configuration Tests
# =============================================================================

class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    def test_cors_allows_get_requests(self, client):
        """Test that CORS allows GET requests."""
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 200

    def test_cors_allows_post_requests(self, client):
        """Test that CORS allows POST requests."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ExecuteResponse(
                success=True,
                content="Test",
                content_type="text",
                tools_used=[],
                tool_outputs=None,
                metadata=None,
                error=None
            )

            response = client.post(
                "/execute",
                json={
                    "user_id": "user_123",
                    "channel_id": "channel_456",
                    "message": "Test"
                },
                headers={"Origin": "http://localhost:3000"}
            )
            assert response.status_code == 200

    def test_cors_preflight_options_request(self, client):
        """Test that CORS handles preflight OPTIONS requests."""
        response = client.options(
            "/execute",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )
        # Should return 200 for preflight
        assert response.status_code == 200


# =============================================================================
# Request Validation Tests
# =============================================================================

class TestRequestValidation:
    """Tests for request validation."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_json(self):
        """Test that invalid JSON is rejected."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                content="not valid json",
                headers={"Content-Type": "application/json"}
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validates_user_id_max_length(self):
        """Test that user_id max length is validated."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                json={
                    "user_id": "x" * 200,  # Exceeds max_length of 128
                    "channel_id": "channel_456",
                    "message": "Test"
                }
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validates_message_max_length(self):
        """Test that message max length is validated."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/execute",
                json={
                    "user_id": "user_123",
                    "channel_id": "channel_456",
                    "message": "x" * 10001  # Exceeds max_length of 10000
                }
            )

        assert response.status_code == 422


# =============================================================================
# Response Schema Tests
# =============================================================================

class TestResponseSchema:
    """Tests for response schema compliance."""

    @pytest.mark.asyncio
    async def test_execute_response_schema(self, mock_execute_response):
        """Test that execute response matches expected schema."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_execute_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Test"
                    }
                )

            data = response.json()

            # Verify required fields
            assert "success" in data
            assert "content" in data
            assert "content_type" in data
            assert "tools_used" in data

            # Verify types
            assert isinstance(data["success"], bool)
            assert isinstance(data["content"], str)
            assert isinstance(data["content_type"], str)
            assert isinstance(data["tools_used"], list)

    def test_health_response_schema_compliance(self, client):
        """Test that health response matches HealthResponse schema."""
        response = client.get("/health")
        data = response.json()

        # All fields from HealthResponse should be present
        required_fields = ["status", "version", "llm_provider"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


# =============================================================================
# Error Response Tests
# =============================================================================

class TestErrorResponses:
    """Tests for error response formatting."""

    @pytest.mark.asyncio
    async def test_400_error_has_detail(self):
        """Test that 400 errors include detail message."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = ValueError("Test error message")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Test"
                    }
                )

            data = response.json()
            assert "detail" in data
            assert data["detail"] == "Test error message"

    @pytest.mark.asyncio
    async def test_403_error_has_detail(self):
        """Test that 403 errors include detail message."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = PermissionError("Forbidden action")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Test"
                    }
                )

            data = response.json()
            assert "detail" in data
            assert data["detail"] == "Forbidden action"

    @pytest.mark.asyncio
    async def test_500_error_hides_internal_details(self):
        """Test that 500 errors don't expose internal error details."""
        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = RuntimeError("Secret internal error")

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Test"
                    }
                )

            data = response.json()
            # Should not expose internal error message
            assert "Secret internal error" not in data["detail"]
            assert "Internal server error" in data["detail"]

    def test_404_for_unknown_endpoint(self, client):
        """Test that unknown endpoints return 404."""
        response = client.get("/unknown/endpoint")
        assert response.status_code == 404

    def test_405_for_wrong_method(self, client):
        """Test that wrong HTTP methods return 405."""
        response = client.delete("/health")
        assert response.status_code == 405


# =============================================================================
# Integration-like Tests (with mocked dependencies)
# =============================================================================

class TestExecuteIntegration:
    """Integration-style tests for the execute flow."""

    @pytest.mark.asyncio
    async def test_full_execute_flow_success(self):
        """Test a complete successful execute flow."""
        mock_response = ExecuteResponse(
            success=True,
            content="Your channel has grown 15% this week",
            content_type="insight",
            tools_used=["fetch_analytics", "generate_insight"],
            tool_outputs={
                "fetch_analytics": {"views": 15420, "subscribers": 1250},
                "generate_insight": {"insights": ["Strong growth"]}
            },
            metadata={
                "intent": "insight",
                "confidence": 0.92,
                "planning": {"tools_planned": 2, "tools_executed": 2}
            },
            error=None
        )

        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_pro_123",
                        "channel_id": "youtube_channel_abc",
                        "message": "Give me insights on my channel growth",
                        "metadata": {"user_plan": "pro"}
                    }
                )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["content_type"] == "insight"
            assert len(data["tools_used"]) == 2
            assert "fetch_analytics" in data["tools_used"]
            assert "generate_insight" in data["tools_used"]

    @pytest.mark.asyncio
    async def test_execute_with_partial_failure(self):
        """Test execute when some tools fail but request succeeds."""
        mock_response = ExecuteResponse(
            success=True,
            content="Partial results available",
            content_type="analytics",
            tools_used=["fetch_analytics"],
            tool_outputs={"fetch_analytics": {"views": 100}},
            metadata={"intent": "analytics"},
            error="compute_metrics: Tool execution timed out"
        )

        with patch("server.execute_context_request", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/execute",
                    json={
                        "user_id": "user_123",
                        "channel_id": "channel_456",
                        "message": "Show analytics and metrics"
                    }
                )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["error"] is not None  # Contains partial error info


# =============================================================================
# User Status Endpoint Tests (FORCE_PRO_MODE Plan Enforcement)
# =============================================================================

class TestUserStatusEndpoint:
    """Tests for /api/v1/user/status — plan enforcement via FORCE_PRO_MODE."""

    @pytest.mark.asyncio
    async def test_user_status_pro_mode(self):
        """FORCE_PRO_MODE=true → returns plan 'pro' with no usage object."""
        with patch("server.config") as mock_config:
            mock_config.flags.force_pro_mode = True

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                response = await ac.get(
                    "/api/v1/user/status",
                    params={"user_id": "user_123"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["user_plan"] == "pro"
            assert data["usage"] is None

    @pytest.mark.asyncio
    async def test_user_status_free_mode(self):
        """FORCE_PRO_MODE=false → returns plan 'free' with usage object."""
        with patch("server.config") as mock_config:
            mock_config.flags.force_pro_mode = False

            # Mock Redis to return usage count of 0
            with patch("memory.redis_store.RedisMemoryStore") as mock_store_cls:
                mock_store = MagicMock()
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=None)
                mock_store._ensure_connection = AsyncMock(return_value=mock_client)
                mock_store_cls.return_value = mock_store

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as ac:
                    response = await ac.get(
                        "/api/v1/user/status",
                        params={"user_id": "user_123"},
                    )

            assert response.status_code == 200
            data = response.json()
            assert data["user_plan"] == "free"
            assert data["usage"] is not None
            assert data["usage"]["used"] == 0
            assert data["usage"]["limit"] == 3
            assert data["usage"]["exhausted"] is False

    @pytest.mark.asyncio
    async def test_user_status_free_exhausted(self):
        """FORCE_PRO_MODE=false with usage at limit → exhausted=true."""
        with patch("server.config") as mock_config:
            mock_config.flags.force_pro_mode = False

            with patch("memory.redis_store.RedisMemoryStore") as mock_store_cls:
                mock_store = MagicMock()
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=b"3")
                mock_store._ensure_connection = AsyncMock(return_value=mock_client)
                mock_store_cls.return_value = mock_store

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as ac:
                    response = await ac.get(
                        "/api/v1/user/status",
                        params={"user_id": "user_123"},
                    )

            assert response.status_code == 200
            data = response.json()
            assert data["user_plan"] == "free"
            assert data["usage"]["used"] == 3
            assert data["usage"]["limit"] == 3
            assert data["usage"]["exhausted"] is True
