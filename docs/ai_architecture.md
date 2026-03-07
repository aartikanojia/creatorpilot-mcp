# CreatorPilot MCP — Phase 2 Architecture

> **Frozen:** 2026-03-07  
> Purpose: Lock Phase 2 design decisions to prevent architectural regression.

---

## 1. System Overview

CreatorPilot MCP is a **deterministic analytics intelligence server** for YouTube creators.
It receives user messages via a FastAPI HTTP endpoint, routes them through a series of
deterministic analytics engines, and returns creator-friendly responses.

**Core design principle:** All analytics computation is deterministic Python — no LLM is
involved in constraint analysis, severity scoring, or strategy ranking. LLM is used
only for natural language narration of pre-computed results.

```
Flutter App → API Gateway → MCP Server (FastAPI)
                                ├── Executor (routing + orchestration)
                                ├── Analytics Engines (deterministic)
                                ├── Memory (Redis + PostgreSQL)
                                ├── LLM (Gemini / Azure — narration only)
                                └── YouTube APIs (data + analytics)
```

---

## 2. Project Structure

```
creatorpilot-mcp/
├── server.py                  # FastAPI app, endpoints, CORS
├── config.py                  # Configuration management
├── executor/
│   ├── execute.py             # ContextOrchestrator — main routing
│   ├── planner.py             # ExecutionPlanner — intent classification
│   └── formatter.py           # ResponseFormatter — output formatting
├── analytics/                 # Deterministic engines (NO LLM)
│   ├── strategy_ranker.py     # StrategyRankingEngine — ranked strategies
│   ├── video_diagnosis.py     # VideoDiagnosisEngine — per-video diagnosis
│   ├── retention_diagnosis.py # RetentionDiagnosisEngine — retention analysis
│   ├── diagnostics.py         # Core diagnostic functions
│   ├── archetype.py           # ArchetypeAnalyzer — channel identity
│   ├── strategy.py            # Strategy framework computation
│   ├── patterns.py            # Cross-video pattern detection
│   ├── premium_formatter.py   # PremiumOutputFormatter — structured output
│   ├── scope_guard.py         # ScopeGuardLayer — analysis boundary enforcement
│   ├── context_builder.py     # AnalyticsContextBuilder
│   ├── channel_orchestrator.py
│   ├── video_orchestrator.py
│   ├── normalizer.py          # Traffic source normalization
│   ├── fetcher.py             # YouTube Analytics API fetcher
│   ├── conversion_rate_analyzer.py
│   ├── ctr_diagnosis.py
│   ├── growth_trend_engine.py
│   ├── shorts_impact_analyzer.py
│   ├── thumbnail_quality_engine.py
│   ├── thumbnail_scoring.py
│   ├── topic_pattern_analyzer.py
│   ├── next_video_blueprint_engine.py
│   ├── unified_engine_orchestrator.py
│   └── weekly_summary_generator.py
├── db/
│   ├── models/
│   │   ├── user.py
│   │   ├── channel.py         # OAuth tokens + channel_name
│   │   ├── video.py
│   │   ├── video_snapshot.py
│   │   ├── analytics_snapshot.py
│   │   ├── chat_session.py
│   │   └── weekly_insight.py
│   ├── base.py
│   └── session.py
├── memory/
│   ├── redis_store.py         # Short-term memory + usage tracking
│   └── postgres_store.py      # Long-term conversation history
├── llm/
│   ├── langchain_gemini.py    # Google Gemini integration
│   └── langchain_azure.py     # Azure OpenAI integration
├── registry/
│   ├── tools.py               # ToolRegistry — tool definitions
│   ├── schemas.py             # Pydantic request/response models
│   ├── policies.py            # PolicyEngine — plan enforcement
│   └── tool_handlers/         # Individual tool implementations
├── services/
│   └── video_resolver.py      # Video title → DB record resolution
├── prompts/
│   └── system.txt             # LLM system prompt
└── tests/                     # 941 tests (Phase 2 complete)
```

---

## 3. Request Flow

### 3.1 Main Execution Pipeline

```
POST /execute { user_id, channel_id, message }
  │
  ├─ 1. Load memory context (Redis + PostgreSQL)
  ├─ 2. Inject channel context (OAuth tokens, channel_name)
  ├─ 3. Plan tool execution (intent classification)
  ├─ 4. Execute approved tools
  │
  ├─ 4.5a  Conversational intercept (name queries)     → RETURN
  ├─ 4.5b  Identity intercept (archetype queries)       → RETURN
  ├─ 4.6   Structural analysis (strategy ranking)       → RETURN
  ├─ 4.7   Video diagnosis bypass (per-video analysis)  → RETURN
  ├─ 4.8   Weekly summary bypass                        → RETURN
  │
  ├─ 5. Build LLM prompt (with pre-computed analytics)
  ├─ 6. Call LLM (narration only)
  ├─ 7. Format response
  └─ 8. Store conversation + persist to PostgreSQL
```

### 3.2 Intercept / Bypass Priority (Top → Bottom)

| Priority | Route | Trigger | LLM Used? |
|----------|-------|---------|-----------|
| 1 | **Conversational** | `"what's my name"`, `"who am i"` patterns | ❌ No |
| 2 | **Identity** | `"channel archetype"`, `"diagnose my channel"` patterns | ❌ No |
| 3 | **Structural Analysis** | `intent == "structural_analysis"` + channel connected | ❌ No |
| 4 | **Video Diagnosis** | Video-specific analysis query + video resolved | ❌ No |
| 5 | **Weekly Summary** | Weekly performance query | ❌ No |
| 6 | **LLM Fallthrough** | No bypass matched | ✅ Yes (narration) |

---

## 4. Analytics Engines

### 4.1 Strategy Ranking Engine (`strategy_ranker.py`)

**Input:** `ChannelMetrics(retention, ctr, conversion, shorts_ratio, theme_concentration)`  
**Output:** `StrategyResult(primary_constraint, severity_score, ranked_strategies, confidence)`

Priority order (strict):
1. Critical severity (≥ 0.9): Retention > CTR > Conversion
2. Moderate severity (≥ 0.6): Retention > CTR > Conversion
3. Structural risks (theme/format) — only if metrics stable
4. Default — Pattern Scaling

### 4.2 Video Diagnosis Engine (`video_diagnosis.py`)

**Input:** `video_avg_view_percentage, video_watch_time_minutes, video_length_minutes, video_ctr, impressions, format_type`  
**Output:** Constraint diagnosis dict

Diagnoses: Retention weakness, CTR weakness, Distribution weakness.

**Cold-start guard:** If `impressions < 10`, returns `insufficient_data` — no false diagnoses.

### 4.3 Retention Diagnosis Engine (`retention_diagnosis.py`)

**Input:** `avg_view_percentage, avg_watch_time_minutes, avg_video_length_minutes, shorts_ratio, long_form_ratio`  
**Output:** Severity score, risk level, amplifiers, confidence

### 4.4 Premium Output Formatter (`premium_formatter.py`)

Accepts structured intelligence state and formats for creator display.

**Allowed keys:** `primary_constraint`, `severity`, `ranked_strategies`, `confidence`, `video_title` (optional)

**Features:**
- Constraint → human-readable title translation
- Deterministic improvement suggestion per constraint
- Video title prepended when available
- Risk Level, Shorts Ratio, Watch Time Ratio **excluded** from output

### 4.5 Scope Guard (`scope_guard.py`)

Enforces analysis boundaries — prevents channel-level data from leaking into video-level analysis and vice versa.

---

## 5. Presentation Rules (Phase 2)

### 5.1 Severity Labels

All numeric severity scores (0.0–1.0) are translated to creator-friendly labels:

| Score Range | Label |
|-------------|-------|
| ≥ 0.9 | **Critical** |
| ≥ 0.7 | **High** |
| ≥ 0.5 | **Moderate** |
| ≥ 0.3 | **Early Warning** |
| < 0.3 | **Stable** |

Applied via `ContextOrchestrator.severity_label()` across all output paths.

### 5.2 Hidden from Creator Output

These fields are **internal engine diagnostics** and must NOT appear in responses:
- Risk Level
- Shorts Ratio
- Watch Time Ratio
- Retention Diagnosis block (in strategy bypass)

### 5.3 Visible in Creator Output

- Primary Constraint (with human-readable title + explanation)
- Suggested Improvement (deterministic per constraint)
- Severity (as label, not number)
- Strategy Ranking
- Confidence
- Video Title (when analyzing specific video)

### 5.4 Constraint Suggestions

Deterministic, no-LLM improvement recommendations:

| Constraint | Suggestion |
|------------|------------|
| CTR | Update title/thumbnail to highlight most exciting visual moment |
| Retention | Move most interesting moment to beginning, remove slow intros |
| Conversion | Add clear subscribe moment after delivering value |
| Shorts | Create longer-form companion video from best Short |
| Growth | Analyze top 3 videos, create content following same patterns |

### 5.5 Cold-Start Guard

Videos with `impressions < 10` receive:
```
Video Analysis: {title}

This video has not received enough views yet to evaluate performance.

Allow the video to gather more viewer activity before analyzing its performance.
```

No constraint severity assigned. No false diagnosis.

---

## 6. Conversational Handling

### 6.1 Name / Identity Queries

**Patterns:** `"what's my name"`, `"what is my channel name"`, `"who am i"`

**Behavior:**
- If channel connected → `"Your channel name is **{channel_name}**."`
- If no channel → `"I don't have your channel name yet. Please connect your YouTube channel."`
- No analytics engines triggered
- Returns `ExecuteResponse` with `intent: "conversational"`

### 6.2 Archetype Queries

**Patterns:** `"what type of channel"`, `"channel identity"`, `"diagnose my channel"`

**Behavior:** Computes and renders archetype deterministically. No LLM.

---

## 7. Data Models

### 7.1 Database (PostgreSQL)

| Model | Table | Key Fields |
|-------|-------|------------|
| `User` | `users` | `id (UUID)` |
| `Channel` | `channels` | `user_id, youtube_channel_id, channel_name, access_token, refresh_token` |
| `Video` | `videos` | `channel_id, youtube_video_id, title, statistics` |
| `VideoSnapshot` | `video_snapshots` | Point-in-time video metrics |
| `AnalyticsSnapshot` | `analytics_snapshots` | Channel-level analytics |
| `ChatSession` | `chat_sessions` | Conversation history |
| `WeeklyInsight` | `weekly_insights` | Pre-computed weekly summaries |

### 7.2 Memory Layer

| Store | Purpose |
|-------|---------|
| **Redis** | Short-term memory, session state, daily usage counters (`usage:{user_id}:{date}`) |
| **PostgreSQL** | Long-term conversation history, analytics snapshots, insights |

---

## 8. API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/execute` | Main MCP execution endpoint |
| `GET` | `/health` | Container health check |
| `GET` | `/api/v1/user/status` | User plan + usage (no increment) |
| `POST` | `/channels/connect` | OAuth channel connection (upsert) |
| `GET` | `/channels/{user_id}/stats` | Real YouTube channel statistics |
| `GET` | `/analytics/top-video` | Most-watched video for period |

---

## 9. LLM Integration

| Provider | Module | Usage |
|----------|--------|-------|
| Google Gemini | `llm/langchain_gemini.py` | Primary LLM provider |
| Azure OpenAI | `llm/langchain_azure.py` | Fallback LLM provider |

**LLM is used ONLY for narration** — converting pre-computed structured output into
natural language. All constraint analysis, severity scoring, strategy ranking, and
diagnostic logic is deterministic Python.

---

## 10. Plan Enforcement

| Plan | Daily Limit | Behavior |
|------|-------------|----------|
| **Free** | 3 requests/day | After limit: returns `PLAN_LIMIT_REACHED` |
| **Pro** | Unlimited | Full access to all features |

Usage tracked via Redis keys: `usage:{user_id}:{YYYY-MM-DD}`

`FORCE_PRO_MODE` config flag overrides plan to `pro` for development.

---

## 11. Test Coverage

**941 tests passing** (Phase 2 complete)

Key test files:
- `tests/test_orchestrator.py` — Executor routing and intercepts
- `tests/test_premium_formatter.py` — Output formatting rules
- `tests/test_video_diagnosis.py` — Video-level diagnosis
- `tests/test_strategy_ranker.py` — Strategy ranking engine
- `tests/test_retention_diagnosis.py` — Retention analysis

---

## 12. Architectural Invariants

> **These rules MUST NOT be violated in future phases.**

1. **No LLM in analytics computation.** All constraint analysis, severity scoring, and
   strategy ranking is deterministic Python.

2. **Severity is always a label.** Never show raw numeric scores (0.0–1.0) to creators.

3. **Scope guard enforced.** Video-level analysis never uses channel-level averages.
   Channel-level analysis never uses single-video data.

4. **No internal diagnostics in output.** Risk Level, Shorts Ratio, Watch Time Ratio
   are engine internals — never shown to creators.

5. **Cold-start guard active.** Videos with < 10 impressions get "insufficient data"
   instead of a diagnosis.

6. **Conversational queries bypass analytics.** Name/identity questions never trigger
   analytics engines.

7. **All bypass paths return `ExecuteResponse`.** Never return raw strings from the
   executor — the server expects structured response objects.

8. **Improvement suggestions are deterministic.** One mapping per constraint type,
   no LLM involved.
