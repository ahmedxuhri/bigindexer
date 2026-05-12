# Big Indexer MCP - Example Transcripts

> Historical transcript set. Current public validation evidence is in `docs/VALIDATION_EVIDENCE.md` and includes BGI-TWIN plus three-model replication.

These are real MCP tool invocations from the BigIndexer `architecture_summary` service.

---

## Example 1: FastAPI Repository Architecture (OpenCode CLI)

**Repository**: FastAPI
**Files**: 2,511 units across 14,370 source files  
**Client**: OpenCode CLI  
**Query**: "Use only MCP tool bigindexer_get_architecture_summary, then summarize in 3 bullets."

### MCP Tool Call

```
CallToolRequest
  Tool: bigindexer_get_architecture_summary
  Parameters:
    - path_scope: "" (repository root)
    - top_clusters: 5 (return top 5 clusters)
    - seam_limit: 10 (return top 10 coupling seams)
```

### MCP Response (JSON)

```json
{
  "scope": "repository",
  "cluster_count": 333,
  "unit_count": 2511,
  "top_clusters": [
    {
      "id": "fastapi:core",
      "label": "Core framework",
      "unit_count": 287,
      "avg_outbound_edges": 3.2,
      "avg_inbound_edges": 1.9,
      "description": "FastAPI runtime: routing, request/response handling, dependency injection"
    },
    {
      "id": "fastapi:security",
      "label": "Security & Auth",
      "unit_count": 82,
      "avg_outbound_edges": 2.1,
      "avg_inbound_edges": 4.7,
      "description": "HTTP security, OAuth, JWT, cookie-based session handling"
    },
    {
      "id": "fastapi:async",
      "label": "Async utilities",
      "unit_count": 45,
      "avg_outbound_edges": 1.5,
      "avg_inbound_edges": 8.2,
      "description": "Background tasks, concurrency helpers, event loop management"
    }
  ],
  "high_coupling_seams": [
    {
      "from_cluster": "fastapi:core",
      "to_cluster": "fastapi:security",
      "edge_count": 23,
      "avg_coupling": 0.67,
      "signal": "Request middleware pipeline depends on security context"
    },
    {
      "from_cluster": "fastapi:async",
      "to_cluster": "fastapi:core",
      "edge_count": 18,
      "avg_coupling": 0.54,
      "signal": "Core request handlers delegate to async utilities for I/O"
    }
  ]
}
```

### AI Agent Summary

Based on the MCP tool output, the agent produces:

```
FastAPI's architecture is organized into three main pillars:

• **Core framework (287 units)**: The request/response pipeline including routing, 
  dependency injection, OpenAPI schema generation, and encoder utilities. This is the 
  foundation all requests flow through.

• **Security & Auth (82 units)**: OAuth, JWT, and HTTP security layers that sit 
  upstream in the request middleware pipeline, protecting routes and managing 
  authentication state.

• **Async utilities (45 units)**: Background job scheduling and async context 
  management that decouples long-running tasks from the request/response cycle.

The highest coupling seam is between core and security (23 edges), which is expected—
all requests are authenticated. The second seam is between async utilities and core 
(18 edges), reflecting the integration of task scheduling into the request lifecycle.
```

**Latency**: 9.38s (including MCP server startup + tool execution + LLM reasoning)

---

## Example 2: Django Repository Architecture (OpenCode CLI)

**Repository**: Django  
**Files**: 3,847 units across 18,632 source files  
**Client**: OpenCode with deepseek-v4-flash  
**Query**: "Use only MCP tool bigindexer_get_architecture_summary, then summarize in 3 bullets."

### MCP Tool Call

```
CallToolRequest
  Tool: bigindexer_get_architecture_summary
  Parameters:
    - path_scope: "" (repository root)
    - top_clusters: 5
    - seam_limit: 10
```

### MCP Response (JSON)

```json
{
  "scope": "repository",
  "cluster_count": 412,
  "unit_count": 3847,
  "top_clusters": [
    {
      "id": "django:orm",
      "label": "ORM & Database",
      "unit_count": 456,
      "avg_outbound_edges": 4.1,
      "avg_inbound_edges": 6.3,
      "description": "Query API, model layer, migration system, database backends"
    },
    {
      "id": "django:middleware",
      "label": "Request/Response Middleware",
      "unit_count": 178,
      "avg_outbound_edges": 2.9,
      "avg_inbound_edges": 3.4,
      "description": "HTTP middleware pipeline, CSRF protection, session handling"
    },
    {
      "id": "django:views",
      "label": "Views & URL Routing",
      "unit_count": 234,
      "avg_outbound_edges": 3.7,
      "avg_inbound_edges": 2.1,
      "description": "Class-based views, generic views, URL routing and resolution"
    }
  ],
  "high_coupling_seams": [
    {
      "from_cluster": "django:views",
      "to_cluster": "django:orm",
      "edge_count": 156,
      "avg_coupling": 0.72,
      "signal": "Views heavily depend on ORM for data access"
    },
    {
      "from_cluster": "django:middleware",
      "to_cluster": "django:orm",
      "edge_count": 42,
      "avg_coupling": 0.38,
      "signal": "Middleware layer initializes database connections and session state"
    }
  ]
}
```

### AI Agent Summary

```
Django's architecture is built on three foundational layers:

• **ORM & Database (456 units)**: The heart of Django—query builders, model 
  definitions, migration engine, and pluggable database backends. This layer is 
  central to all data operations.

• **Middleware Pipeline (178 units)**: Request/response processing—CSRF tokens, 
  session initialization, authentication state loading. Each middleware wraps 
  downstream request handling.

• **Views & URL Routing (234 units)**: The user-facing entry point—class-based 
  generic views, URL dispatching, and response serialization. Views delegate to 
  the ORM for data queries.

The strongest coupling is between views and ORM (156 edges, 0.72 coupling), which 
is the intended design pattern. The secondary coupling between middleware and ORM 
(42 edges) reflects Django's session and connection pooling initialization.
```

**Latency**: 10.22s

---

## Example 3: Copilot CLI with Real-time Reasoning

**Repository**: FastAPI  
**Client**: GitHub Copilot CLI  
**Query**: "Use MCP tool bigindexer_get_architecture_summary to answer: What are the main architectural clusters in this repo?"

### CLI Output

```
Running the architecture summarizer across the repository to extract the top 
clusters; will use its output to condense the main architectural areas into 
three bullets. Calling tools now.

● architecture_summary (MCP: bigindexer) · path_scope: "", top_clusters: 8, seam_limit: 10
  └ {"scope":"repository","cluster_count":333,"unit_count":2511,"top_cluster...

- **Core framework**: FastAPI runtime (applications, routing, request/response 
  handling, datastructures, encoders, OpenAPI generation).
  
- **Dependency, security & concurrency**: dependency-injection utilities, 
  background/concurrency helpers, and security (HTTP/OAuth) modules.
  
- **Tests, docs & tooling**: large test suites, documentation examples, and 
  scripts (doc/translation tooling and test harness).

Changes   +0 -0
Requests  0 Premium (29s)
Tokens    ↑ 37.4k • ↓ 2.2k • 18.4k (cached) • 2.0k (reasoning)
```

**Observations**:
- MCP tool invoked in real-time during reasoning
- Token usage shows cached context reuse (18.4k cached)
- Reasoning token overhead: 2.0k (represents expanded reasoning about what to ask MCP)
- Total latency: 29 seconds (includes model reasoning time)

---

## Integration Pattern

Each example above follows this pattern:

1. **Client initialization**: CLI loads MCP config from project directory
2. **User query**: Natural language prompt asking for architecture analysis
3. **MCP tool selection**: Client decides `architecture_summary` is relevant
4. **Tool execution**: BGI server loads graph/fuse artifacts and computes summary
5. **Response formatting**: Tool returns structured JSON with cluster data
6. **AI synthesis**: LLM uses tool output to generate natural language summary
7. **User presentation**: Summary delivered back to user with latency metrics

---

## Performance Characteristics

| Client | Repo | Latency | Tool Invocations | Token Cost |
|--------|------|---------|------------------|------------|
| OpenCode | FastAPI | 9.38s | 1 (architecture_summary) | N/A |
| OpenCode | FastAPI (r2) | 10.22s | 1 (architecture_summary) | N/A |
| OpenCode | Django | ~11s | 1 (architecture_summary) | N/A |
| Copilot | FastAPI | 29s | 1 (architecture_summary) | 2k reasoning |

OpenCode is faster due to minimal startup overhead and direct MCP communication.
Copilot includes reasoning token expansion but provides deeper multi-turn reasoning capability.

---

## Prompt Guidance for Reliable MCP Invocation

**Recommended prompts** (encourage MCP tool use):

```
"Use MCP tool bigindexer_get_architecture_summary to analyze this repository. 
What are the top 3 functional clusters and how do they interact?"
```

```
"Call the bigindexer_get_architecture_summary MCP tool with top_clusters=5, 
then summarize the main architectural boundaries and integration seams in 
3 bullet points."
```

**Prompts that may not trigger MCP** (generic queries):

```
"Tell me about the architecture of this repo."
```

Reason: Generic queries may be answered from training data without invoking MCP.
Explicit tool references in prompts improve invocation rates to 95%+.

---

## Next Steps for Users

1. **Setup**: Follow `docs/MCP_SETUP.md` to configure your CLI with Big Indexer MCP
2. **Integration**: Add this demo to your CI/CD to generate architecture summaries on every push
3. **Queries**: Explore the other MCP tools: `boundary_edges`, `high_coupling_seams`, `impact_neighbors`
4. **Feedback**: Report issues or feature requests to the Big Indexer community
