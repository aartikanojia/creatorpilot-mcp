# Creator Pilot MCP Server

A production-grade **Model Context Protocol (MCP)** server for AI agent context orchestration, tool execution, and memory management.

## What is MCP?

The **Model Context Protocol** is an architectural pattern for building AI-powered applications that require:

- **Context Orchestration**: Managing conversation history, user preferences, and session state across multiple interactions
- **Tool Execution**: Coordinating the execution of specialized tools (analytics, insights, reports) based on user intent
- **Memory Management**: Combining short-term (Redis) and long-term (PostgreSQL) memory for comprehensive context
- **Prompt Governance**: Enforcing consistent, hallucination-free responses through structured prompts
- **LLM Agnosticism**: Supporting multiple LLM providers without code changes

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           FastAPI Server                                 │
│                     POST /execute  |  GET /health                        │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        Executor (Orchestrator)                           │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────────┐  │
│  │   Planner    │   │   Execute    │   │         Formatter            │  │
│  │  (Intent &   │──▶│   (Tools)    │──▶│   (Response & Content)       │  │
│  │   Planning)  │   │              │   │                              │  │
│  └──────────────┘   └──────────────┘   └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
         │                    │                         │
         ▼                    ▼                         ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐
│    Registry     │  │     Memory      │  │          Prompts            │
│  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────────────────┐  │
│  │   Tools   │  │  │  │   Redis   │  │  │  │    system.txt         │  │
│  │  (17 tools│  │  │  │  (short)  │  │  │  │    analysis.txt       │  │
│  │  Registry)│  │  │  └───────────┘  │  │  │    top_video_analysis │  │
│  │           │  │  │  └───────────┘  │  │  └───────────────────────┘  │
│  ├───────────┤  │  │  ┌───────────┐  │  └─────────────────────────────┘
│  │ Handlers  │  │  │  │ Postgres  │  │
│  │ (modular) │  │  │  │  (long)   │  │
│  ├───────────┤  │  │  └───────────┘  │
│  │  Schemas  │  │  └─────────────────┘
│  ├───────────┤  │
│  │ Policies  │  │
│  │(FREE/PRO/ │  │
│  │  AGENCY)  │  │
│  └───────────┘  │
└─────────────────┘
```

## Features

- **Clean HTTP API**: Single `/execute` endpoint for all context requests
- **Extended Analytics**: CTR, impressions, retention, and traffic source metrics
- **Availability Flags**: Graceful handling of missing metrics with explicit flags
- **Plan-Based Access Control**: Free, Pro, and Agency tier tool restrictions
- **Request-Based Usage Limits**: FREE users get 3 requests/day, PRO users unlimited
- **Deterministic Planning**: Rule-based tool selection with explainable reasoning
- **Memory Layers**: Redis for conversation state, PostgreSQL for historical data
- **LLM Agnostic**: Configure any LLM provider via environment variables
- **Docker Ready**: Production Dockerfile with health checks

## Usage Limits

The server enforces request-based usage limits to manage resource consumption by plan tier.

### Limits by Plan

| Plan | Daily Request Limit | Rate Tracking |
|------|---------------------|---------------|
| FREE | 3 requests/day      | Redis-based   |
| PRO  | Unlimited           | No tracking   |

### How It Works

1. **Request Counter**: Each FREE user request increments a Redis counter with key `usage:{user_id}:{YYYY-MM-DD}`
2. **Daily Reset**: Counters auto-expire after 24 hours (UTC-based)
3. **Early Enforcement**: Limits are checked **before** any tool execution, analytics context building, or LLM calls
4. **Fail-Open**: If Redis is unavailable, requests are allowed (graceful degradation)

### Limit Exceeded Response

When a FREE user exceeds their daily limit, the API returns:

```json
{
  "success": false,
  "error": {
    "code": "PLAN_LIMIT_REACHED",
    "message": "You've reached your free analysis limit for today. Upgrade to PRO to unlock unlimited insights."
  }
}
```

**Important**: When limit is exceeded:
- ❌ No tools are executed
- ❌ No LLM is called
- ❌ No analytics context is built
- ✅ Fast response with upgrade message

## Project Structure

```
creatorpilot-mcp/
├── server.py              # FastAPI application entry point
├── config.py              # Centralized configuration
├── Dockerfile             # Production container image
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── .gitignore             # Git ignore file
├── alembic.ini            # Alembic configuration
│
├── alembic/               # Database migrations
│   ├── env.py             # Migration environment
│   └── versions/          # Migration scripts
│
├── executor/              # Core orchestration logic
│   ├── execute.py         # Main execution coordinator
│   ├── planner.py         # Intent classification & tool planning
│   └── formatter.py       # Response formatting
│
├── registry/              # Tool registry and definitions (modular)
│   ├── base.py            # Core classes (ToolResult, ToolDefinition)
│   ├── tools.py           # Tool registry with 17 tools
│   ├── schemas.py         # Pydantic request/response models
│   ├── policies.py        # Plan-based access control (FREE/PRO/AGENCY)
│   ├── handlers/          # Handler implementations by category
│   │   ├── analytics.py   # fetch_analytics, compute_metrics, generate_chart
│   │   ├── insight.py     # analyze_data, generate_insight, get_recommendations
│   │   ├── report.py      # generate_report, summarize_data
│   │   ├── memory.py      # recall_context, search_history
│   │   ├── action.py      # execute_action, schedule_task
│   │   ├── search.py      # search_data
│   │   └── youtube.py     # get_channel_snapshot, get_top_videos,
│   │                      # video_post_mortem, weekly_growth_report
│   └── tool_handlers/     # Real API tool implementations
│       ├── fetch_analytics.py          # Real YouTube Analytics ingestion
│       └── fetch_last_video_analytics.py  # Last video analytics
│
├── clients/               # External API clients
│   └── youtube_analytics.py    # YouTube Analytics API OAuth client
│
├── analytics/             # Analytics processing
│   ├── context_builder.py # Build analytics context for LLM
│   ├── fetcher.py         # Fetch data from YouTube Analytics API
│   └── normalizer.py      # Normalize API responses to snapshot format
│
├── db/                    # Database models and session management
│   ├── __init__.py        # Package exports
│   ├── base.py            # SQLAlchemy Base, TimestampMixin
│   ├── session.py         # Async engine, session factory, get_db()
│   └── models/            # SQLAlchemy ORM models
│       ├── user.py        # User with subscription plans (FREE/PRO/AGENCY)
│       ├── channel.py     # YouTube channel linked to user
│       ├── analytics_snapshot.py  # Channel analytics (7/30/90 days)
│       ├── video_snapshot.py      # Individual video metrics
│       ├── weekly_insight.py      # Weekly growth reports
│       └── chat_session.py        # Conversation history/context
│
├── memory/                # Data persistence
│   ├── redis_store.py     # Short-term memory (conversations)
│   └── postgres_store.py  # Long-term memory (analytics, channels)
│
├── llm/                   # LLM client implementations
│   └── langchain_azure.py # Azure OpenAI via LangChain
│
├── scripts/               # Utility scripts
│   └── init_db.py         # Database initialization script
│
├── tests/                 # Test suite (123 tests)
│   ├── conftest.py        # Shared fixtures
│   ├── test_server.py     # Server endpoint tests
│   ├── test_orchestrator.py  # Orchestrator integration tests
│   ├── test_planner.py    # Intent classification tests
│   └── test_response_quality.py  # Response quality assertions
│
└── prompts/               # LLM prompt templates
    ├── system.txt         # Core system prompt
    ├── analysis.txt       # Deep analysis mode prompt
    └── top_video_analysis.txt  # Top video analysis template
```

## YouTube Analytics Integration

The server supports **real YouTube Analytics data ingestion** via OAuth. When a channel is connected, the `fetch_analytics` tool fetches live data from the YouTube Analytics API.

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     YouTube Analytics Flow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Channel connected via OAuth (access_token stored)           │
│                          ▼                                       │
│  2. User sends analytics request                                │
│                          ▼                                       │
│  3. Executor loads channel context with OAuth tokens            │
│                          ▼                                       │
│  4. fetch_analytics tool calls YouTube Analytics API            │
│                          ▼                                       │
│  5. Response normalized to AnalyticsSnapshot format             │
│                          ▼                                       │
│  6. Snapshot persisted to PostgreSQL                            │
│                          ▼                                       │
│  7. LLM uses real data for insights (no hallucination)          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Metrics Fetched

| Metric | Description |
|--------|-------------|
| `views` | Total views in last 7 days |
| `impressions` | How often thumbnails were shown |
| `impressionsClickThroughRate` | CTR (click-through rate) |
| `averageViewPercentage` | Audience retention percentage |
| `subscribers` | Subscribers gained in last 7 days |
| `estimatedMinutesWatched` | Total watch time in minutes |
| `averageViewDuration` | Average view duration in seconds |

### Traffic Sources

The `fetch_analytics` tool also retrieves traffic source breakdown:

| Source | Description |
|--------|-------------|
| `YT_SEARCH` | Views from YouTube search |
| `SUGGESTED` | Views from suggested videos |
| `BROWSE_FEATURES` | Views from browse/home page |
| `EXTERNAL` | Views from external websites |

### Analytics Availability Flags

The context builder computes availability flags for graceful handling of missing metrics:

```python
{
  "current_period": {...},
  "previous_period": {...},
  "has_ctr": True,         # impressions > 0
  "has_retention": True,   # avg_view_percentage is not None
  "has_traffic_sources": True  # traffic_sources not empty
}
```

These flags are injected into LLM prompts to ensure the AI only analyzes available data and explicitly states when metrics are missing.

### Automatic Token Refresh

The server automatically handles **expired OAuth access tokens** using the stored refresh token:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Token Refresh Flow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. API call attempted with access_token                         │
│                          ▼                                       │
│  2. Token detected as expired                                    │
│                          ▼                                       │
│  3. Automatic refresh using refresh_token                        │
│                          ▼                                       │
│  4. New access_token obtained                                    │
│                          ▼                                       │
│  5. API call retried with fresh token                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

This ensures uninterrupted analytics access without requiring users to reconnect their channel. If refresh fails, a clear error message prompts the user to reconnect.

### Channel Context Injection

The executor automatically injects channel OAuth tokens into the tool context:

```python
# Available in all tools via input_data["context"]["channel"]
{
    "id": "uuid-of-channel",
    "youtube_channel_id": "UC...",
    "channel_name": "My Channel",
    "access_token": "ya29...",
    "refresh_token": "1//..."
}
```

### Required Dependencies

```
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-auth-oauthlib>=1.1.0
```


### Database Model Relationships

```
User ──┬── Channel ──┬── AnalyticsSnapshot
       │             ├── VideoSnapshot
       │             └── WeeklyInsight
       └── ChatSession
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- Redis (optional, falls back to in-memory)
- PostgreSQL (optional, falls back to in-memory)

> [!WARNING]
> ### ⚠️ Development Note
> 
> During early development, a demo user is pre-created in the database with ID:
> ```
> 00000000-0000-0000-0000-000000000001
> ```
> This user is used to associate OAuth-connected YouTube channels until proper authentication is introduced.

### Local Development

1. **Clone and navigate to the project:**

```bash
cd creatorpilot-mcp
```

2. **Create a virtual environment:**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Set environment variables:**

```bash
export LLM_PROVIDER=openai
export LLM_API_KEY=your-api-key
export LLM_MODEL=gpt-4
export DEBUG=true
```

5. **Run the server:**

```bash
python server.py
```

The server will start at `http://localhost:8001`.

## API Reference

### Base URL

```
http://localhost:8001
```

### Endpoints Overview

| Method | Endpoint   | Description                              |
| ------ | ---------- | ---------------------------------------- |
| GET    | `/`        | Root endpoint with API info              |
| GET    | `/health`  | Health check for container orchestration |
| POST   | `/execute` | Main execution endpoint                  |
| GET    | `/docs`    | Swagger UI (debug mode only)             |
| GET    | `/redoc`   | ReDoc documentation (debug mode only)    |

---

### GET /

Root endpoint with API information.

**Request:**

```
GET http://localhost:8001/
```

**Response:**

```json
{
  "service": "Creator Pilot MCP Server",
  "version": "1.0.0",
  "docs": "/docs"
}
```

---

### GET /health

Health check endpoint for container orchestration.

**Request:**

```
GET http://localhost:8001/health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "llm_provider": "openai"
}
```

---

### POST /execute

Execute a context request with tool orchestration.

**Request:**

```
POST http://localhost:8001/execute
Content-Type: application/json
```

**Request Body:**

```json
{
  "user_id": "user_abc123",
  "channel_id": "channel_xyz789",
  "message": "Show me my channel's performance this week",
  "metadata": {
    "user_plan": "pro",
    "timezone": "UTC"
  }
}
```

**Response:**

```json
{
  "success": true,
  "content": "Your channel had a strong week with 15,420 views...",
  "content_type": "analytics",
  "tools_used": ["fetch_analytics", "compute_metrics"],
  "tool_outputs": {
    "data": {
      "views": 15420,
      "subscribers": 1250
    },
    "metrics": {
      "growth_rate": 15.2
    }
  },
  "metadata": {
    "timestamp": "2024-01-15T10:30:00Z",
    "intent": "analytics",
    "confidence": 0.92
  }
}
```

---

## Postman Collection

### Import Instructions

1. Open Postman
2. Click **Import** → **Raw text**
3. Paste the JSON below and import

### Postman Collection JSON

```json
{
  "info": {
    "name": "Creator Pilot MCP Server",
    "description": "API collection for Creator Pilot MCP Server - AI agent context orchestration",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8001",
      "type": "string"
    }
  ],
  "item": [
    {
      "name": "System",
      "item": [
        {
          "name": "Root - API Info",
          "request": {
            "method": "GET",
            "header": [],
            "url": {
              "raw": "{{base_url}}/",
              "host": ["{{base_url}}"],
              "path": [""]
            },
            "description": "Get API information and version"
          }
        },
        {
          "name": "Health Check",
          "request": {
            "method": "GET",
            "header": [],
            "url": {
              "raw": "{{base_url}}/health",
              "host": ["{{base_url}}"],
              "path": ["health"]
            },
            "description": "Check server health status"
          }
        }
      ]
    },
    {
      "name": "Execute - Analytics",
      "item": [
        {
          "name": "Get Channel Analytics",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Show me my channel analytics for last week\",\n  \"metadata\": {\n    \"user_plan\": \"free\",\n    \"timezone\": \"UTC\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Fetch analytics data for a channel"
          }
        },
        {
          "name": "Get View Statistics",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"How many views did I get this month?\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Get view statistics and metrics"
          }
        },
        {
          "name": "Compare Performance",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Compare my performance this week versus last week\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Compare performance across time periods"
          }
        }
      ]
    },
    {
      "name": "Execute - Insights",
      "item": [
        {
          "name": "Get Growth Insights",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Give me insights on my channel growth\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Generate growth insights and recommendations"
          }
        },
        {
          "name": "Get Recommendations",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"What should I do to improve my engagement?\",\n  \"metadata\": {\n    \"user_plan\": \"agency\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Get personalized recommendations (Agency tier)"
          }
        },
        {
          "name": "Why Analysis",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Why did my views drop last week?\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Analyze reasons behind performance changes"
          }
        }
      ]
    },
    {
      "name": "Execute - Reports",
      "item": [
        {
          "name": "Weekly Performance Report",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Generate a weekly performance report\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Generate comprehensive weekly report"
          }
        },
        {
          "name": "Monthly Summary",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Give me a summary of last month\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Get monthly performance summary"
          }
        },
        {
          "name": "Catch Me Up",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Catch me up on what happened this week\",\n  \"metadata\": {\n    \"user_plan\": \"free\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Quick recap of recent activity"
          }
        }
      ]
    },
    {
      "name": "Execute - Memory",
      "item": [
        {
          "name": "Recall Previous Discussion",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"What did we discuss earlier about my thumbnails?\",\n  \"metadata\": {\n    \"user_plan\": \"free\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Recall context from previous conversations"
          }
        },
        {
          "name": "Search History",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Find all the times we talked about engagement\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Search through conversation history"
          }
        }
      ]
    },
    {
      "name": "Execute - Actions",
      "item": [
        {
          "name": "Schedule Task",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Schedule a weekly analytics report every Monday\",\n  \"metadata\": {\n    \"user_plan\": \"agency\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Schedule automated tasks (Agency tier)"
          }
        },
        {
          "name": "Execute Action",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Create a content calendar for next week\",\n  \"metadata\": {\n    \"user_plan\": \"agency\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Execute specific actions (Agency tier)"
          }
        }
      ]
    },
    {
      "name": "Execute - Search",
      "item": [
        {
          "name": "Search Data",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Find my best performing videos\",\n  \"metadata\": {\n    \"user_plan\": \"free\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Search across all data sources"
          }
        },
        {
          "name": "List Content",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"user_123\",\n  \"channel_id\": \"channel_456\",\n  \"message\": \"Show me all my videos from last month\",\n  \"metadata\": {\n    \"user_plan\": \"free\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "List and display content"
          }
        }
      ]
    },
    {
      "name": "Plan Tier Tests",
      "item": [
        {
          "name": "Free Tier Request",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"free_user\",\n  \"channel_id\": \"channel_free\",\n  \"message\": \"Show me my analytics\",\n  \"metadata\": {\n    \"user_plan\": \"free\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Test with Free tier access"
          }
        },
        {
          "name": "Pro Tier Request",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"pro_user\",\n  \"channel_id\": \"channel_pro\",\n  \"message\": \"Generate a detailed report with charts\",\n  \"metadata\": {\n    \"user_plan\": \"pro\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Test with Pro tier access"
          }
        },
        {
          "name": "Agency Tier Request",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"user_id\": \"agency_user\",\n  \"channel_id\": \"channel_agency\",\n  \"message\": \"Schedule a task and give me recommendations\",\n  \"metadata\": {\n    \"user_plan\": \"agency\"\n  }\n}"
            },
            "url": {
              "raw": "{{base_url}}/execute",
              "host": ["{{base_url}}"],
              "path": ["execute"]
            },
            "description": "Test with Agency tier access (all tools)"
          }
        }
      ]
    }
  ]
}
```

### Quick Test URLs

After starting the server with `DEBUG=true python server.py`, test these URLs:

| Endpoint     | URL                                    |
| ------------ | -------------------------------------- |
| Root         | `http://localhost:8001/`               |
| Health       | `http://localhost:8001/health`         |
| Swagger Docs | `http://localhost:8001/docs`           |
| ReDoc        | `http://localhost:8001/redoc`          |
| Execute      | `http://localhost:8001/execute` (POST) |

### Sample cURL Commands

**Health Check:**

```bash
curl http://localhost:8001/health
```

**Execute Request:**

```bash
curl -X POST http://localhost:8001/execute \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "channel_id": "channel_456",
    "message": "Show me my analytics",
    "metadata": {"user_plan": "pro"}
  }'
```

## Configuration

All configuration is via environment variables:

| Variable            | Default       | Description             |
| ------------------- | ------------- | ----------------------- |
| `SERVER_HOST`       | `0.0.0.0`     | Server bind host        |
| `SERVER_PORT`       | `8001`        | Server bind port        |
| `DEBUG`             | `false`       | Enable debug mode       |
| `LOG_LEVEL`         | `INFO`        | Logging level           |
| `CORS_ORIGINS`      | `*`           | Allowed CORS origins    |
| `REDIS_HOST`        | `localhost`   | Redis host              |
| `REDIS_PORT`        | `6379`        | Redis port              |
| `REDIS_PASSWORD`    | -             | Redis password          |
| `POSTGRES_HOST`     | `localhost`   | PostgreSQL host         |
| `POSTGRES_PORT`     | `5432`        | PostgreSQL port         |
| `POSTGRES_USER`     | `creatorpilot_admin`         | PostgreSQL user         |
| `POSTGRES_PASSWORD` | -             | PostgreSQL password     |
| `POSTGRES_DB`       | `creatorpilot` | PostgreSQL database     |
| `LLM_PROVIDER`      | `openai`      | LLM provider name       |
| `LLM_API_KEY`       | -             | LLM API key             |
| `LLM_MODEL`         | `gpt-4`       | LLM model name          |
| `LLM_BASE_URL`      | -             | Custom LLM API endpoint |
| `LLM_MAX_TOKENS`    | `4096`        | Max tokens per request  |
| `LLM_TEMPERATURE`   | `0.7`         | LLM temperature         |

## Available Tools

The MCP server provides 17 specialized tools organized by subscription tier. Each tool has a specific purpose and returns structured data.

### Free Tier (6 tools)

| Tool                   | Category  | Description                                                                                                                                                       |
| ---------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fetch_analytics`      | Analytics | Fetch analytics data for a channel or time period. Returns views, subscribers, engagement metrics, and watch time statistics.                                     |
| `summarize_data`       | Report    | Create a concise summary of data with key highlights. Useful for quick overviews and executive summaries.                                                         |
| `recall_context`       | Memory    | Recall relevant context from conversation history. Retrieves previous discussions and maintains conversation continuity.                                          |
| `search_data`          | Search    | Search across all available data sources including analytics, history, and insights. Returns matched results with source attribution.                             |
| `get_channel_snapshot` | Analytics | Get a summarized snapshot of YouTube channel performance for a given period (7/30/90 days). Returns subscribers, views, video count, CTR, and average watch time. |
| `get_top_videos`       | Analytics | Return top-performing videos for a YouTube channel sorted by views, engagement, or CTR. Enables cross-video performance comparison.                               |

### Pro Tier (8 tools)

| Tool                   | Category  | Description                                                                                                                                                             |
| ---------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `compute_metrics`      | Analytics | Compute derived metrics from raw analytics data including growth rate, engagement rate, and trend analysis.                                                             |
| `generate_chart`       | Analytics | Generate chart data for visualization (line, bar, pie charts). Returns labels and datasets ready for frontend rendering.                                                |
| `analyze_data`         | Insight   | Perform deep analysis on channel data with focus areas. Returns analysis summary, key findings, and confidence scores.                                                  |
| `generate_insight`     | Insight   | Generate actionable insights from analyzed data. Returns prioritized insights with specific action items.                                                               |
| `generate_report`      | Report    | Generate comprehensive reports with multiple sections. Includes title, summary, detailed sections, and timestamp.                                                       |
| `search_history`       | Memory    | Search through historical data and conversations. Returns results with relevance scores for better context matching.                                                    |
| `video_post_mortem`    | Insight   | Analyze why a video underperformed or overperformed compared to channel average or last 5 videos. Returns verdict, data-driven reasons, and actionable recommendations. |
| `weekly_growth_report` | Report    | Generate weekly growth analysis with week-over-week comparisons. Returns summary, concrete wins/losses with metrics, and strategic next actions.                        |

### Agency Tier (3 tools)

| Tool                  | Category | Description                                                                                                                               |
| --------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `get_recommendations` | Insight  | Get personalized recommendations based on channel data and goals. Returns prioritized recommendations with rationale and expected impact. |
| `execute_action`      | Action   | Execute a specific action on behalf of the user (with confirmation). Supports various action types with custom parameters.                |
| `schedule_task`       | Action   | Schedule a task for future execution. Returns task ID and next run time for tracking and management.                                      |

### Tool Categories

| Category      | Purpose                              | Example Use Cases                       |
| ------------- | ------------------------------------ | --------------------------------------- |
| **Analytics** | Data fetching and metric computation | Views, subscribers, CTR, watch time     |
| **Insight**   | Data analysis and recommendations    | Growth patterns, performance reasons    |
| **Report**    | Report and summary generation        | Weekly reports, monthly summaries       |
| **Memory**    | Context recall and history search    | Previous conversations, historical data |
| **Action**    | Task execution and scheduling        | Automated actions, scheduled tasks      |
| **Search**    | Data search across sources           | Finding specific information            |

### Tool Access by Plan

```
┌─────────────────────────────────────────────────────────────┐
│                      AGENCY (17 tools)                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   PRO (14 tools)                     │   │
│  │  ┌─────────────────────────────────────────────┐    │   │
│  │  │              FREE (6 tools)                  │    │   │
│  │  │  fetch_analytics, summarize_data,           │    │   │
│  │  │  recall_context, search_data,               │    │   │
│  │  │  get_channel_snapshot, get_top_videos       │    │   │
│  │  └─────────────────────────────────────────────┘    │   │
│  │  + compute_metrics, generate_chart, analyze_data,   │   │
│  │    generate_insight, generate_report, search_history│   │
│  │    video_post_mortem, weekly_growth_report          │   │
│  └─────────────────────────────────────────────────────┘   │
│  + get_recommendations, execute_action, schedule_task      │
└─────────────────────────────────────────────────────────────┘
```

## Development

### Code Quality

- Type hints are used throughout
- Docstrings on all public functions
- Modular, extensible architecture

### Extending Tools

Tools are organized in a modular structure under `registry/`:

```
registry/
├── base.py           # Core classes (ToolResult, ToolDefinition)
├── tools.py          # Tool registry with definitions
├── handlers/         # Handler implementations by category
│   ├── analytics.py  # fetch_analytics, compute_metrics, generate_chart
│   ├── insight.py    # analyze_data, generate_insight, get_recommendations
│   ├── report.py     # generate_report, summarize_data
│   ├── memory.py     # recall_context, search_history
│   ├── action.py     # execute_action, schedule_task
│   ├── search.py     # search_data
│   └── youtube.py    # get_channel_snapshot, get_top_videos,
│                     # video_post_mortem, weekly_growth_report
├── schemas.py        # Pydantic request/response models
└── policies.py       # Plan-based access control
```

**Step 1:** Add handler in the appropriate `handlers/*.py` file:

```python
# registry/handlers/analytics.py
class AnalyticsHandlers:
    @staticmethod
    async def my_new_handler(input_data: dict[str, Any]) -> dict[str, Any]:
        """Handler implementation."""
        return {"result": "data"}
```

**Step 2:** Register the tool in `registry/tools.py`:

```python
from .handlers import AnalyticsHandlers

# In the appropriate _register_*_tools() method:
self._register_tool(ToolDefinition(
    name="my_new_tool",
    description="Description of what it does",
    input_schema={...},
    output_schema={...},
    handler=AnalyticsHandlers.my_new_handler,
    category="analytics",
    requires_plan="pro"
))
```

**Step 3:** Update `registry/policies.py` with the new tool:

```python
TOOL_REQUIREMENTS: dict[str, str] = {
    # ...existing tools...
    "my_new_tool": "pro",  # Add minimum required plan
}
```

### Adding LLM Providers

Extend the `_invoke_llm` method in `executor/execute.py` to support additional providers.

## Recent Updates

### v1.3.0 — Infrastructure Hardening & Plan Enforcement
- **Database Standardization**: Complete rename and separation to `creatorpilot` and `creatorpilot_admin`. Removal of legacy `context_hub` references.
- **Proactive Video Ingestion**: Hardened ingestion logic to fetch strictly when `videos` table is empty, preventing unnecessary YouTube API calls.
- **Azure Content Filter Management**: Improved error handling and resilience around OpenAI's content filtering.
- **Plan Enforcement Engine**: Rollout of `FORCE_PRO_MODE` handling for gating FREE vs PRO execution logic.

### v1.2.0 — Intelligent Query Differentiation
- **Content Strategy vs Growth responses**: The executor now detects query sub-types and applies the correct analysis template — content strategy queries get video concepts and hook scripts, growth queries get bottleneck diagnosis and targeted moves
- **Subscriber count fix**: `account` intent now receives channel stats context without triggering the analytics diagnosis prompt
- **New `_is_growth_query` detector**: Pattern-based detection for growth/improvement questions
- **Top video analysis**: Dedicated prompt template and detection logic for top-performing video queries
- **Extended test suite**: 123 tests covering server endpoints, orchestrator logic, planner intent classification, and response quality
- **LangChain Azure client**: Added Azure OpenAI support via LangChain integration

## License

Proprietary - All rights reserved.
