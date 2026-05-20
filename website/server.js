const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const path = require('path');
const fs = require('fs');


const app = express();
const PORT = process.env.PORT || 3200;
const HOST = process.env.HOST || '127.0.0.1';
const TELEMETRY_LOG = process.env.BGI_TELEMETRY_LOG
  || path.join(__dirname, 'data', 'telemetry.jsonl');
const analytics = {
  totalPageviews: 0,
  byPath: new Map(),
  recent: [],
};

function recordPageview({ path: pagePath, title = '', referrer = '', userAgent = '' }) {
  const entry = {
    path: pagePath,
    title,
    referrer,
    userAgent,
    at: new Date().toISOString(),
  };

  analytics.totalPageviews += 1;
  analytics.byPath.set(pagePath, (analytics.byPath.get(pagePath) || 0) + 1);
  analytics.recent.unshift(entry);
  analytics.recent = analytics.recent.slice(0, 50);
}

function getAnalyticsSummary() {
  const byPath = Array.from(analytics.byPath.entries())
    .map(([path, count]) => ({ path, count }))
    .sort((a, b) => b.count - a.count || a.path.localeCompare(b.path));

  return {
    total_pageviews: analytics.totalPageviews,
    unique_paths: analytics.byPath.size,
    by_path: byPath,
    recent: analytics.recent,
  };
}

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// In-memory waitlist (in production, use Azure Table Storage or PostgreSQL)
const waitlist = new Set();

// Health check endpoint (for Azure probe)
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'healthy' });
});

// API: Join waitlist
app.post('/api/waitlist/join', (req, res) => {
  const { email, name } = req.body;

  if (!email || !email.includes('@')) {
    return res.status(400).json({ error: 'Invalid email' });
  }

  if (waitlist.has(email)) {
    return res.status(409).json({ error: 'Email already in waitlist' });
  }

  waitlist.add(email);
  console.log(`New waitlist signup: ${name} (${email}) - Total: ${waitlist.size}`);

  res.status(201).json({
    success: true,
    message: 'Welcome to the Big Indexer waitlist!',
    position: waitlist.size,
    total: waitlist.size
  });
});

// API: Get waitlist status (public)
app.get('/api/waitlist/status', (req, res) => {
  res.json({
    waitlist_size: waitlist.size,
    message: 'People waiting for Big Indexer launch'
  });
});

// API: Pageview analytics
app.post('/api/analytics/pageview', (req, res) => {
  const { path: pagePath, title = '', referrer = '' } = req.body || {};

  if (typeof pagePath !== 'string' || !pagePath.startsWith('/')) {
    return res.status(400).json({ error: 'Invalid path' });
  }

  recordPageview({
    path: pagePath,
    title: typeof title === 'string' ? title : '',
    referrer: typeof referrer === 'string' ? referrer : '',
    userAgent: req.get('user-agent') || '',
  });

  return res.status(204).end();
});

// API: Analytics summary
app.get('/api/analytics/summary', (req, res) => {
  res.json(getAnalyticsSummary());
});

// ── Telemetry (opt-in BGI client pings) ─────────────────────────────────────
// Schema (all fields optional but typed). Anything unrecognized is rejected.
const TELEMETRY_OS_VALUES = new Set(['linux', 'darwin', 'windows', 'other']);
const TELEMETRY_BUCKETS = new Set(['S', 'M', 'L', 'XL']);
const TELEMETRY_KINDS = new Set(['mcp_start', 'tool_call']);

function validateTelemetry(body) {
  if (!body || typeof body !== 'object') return 'invalid body';
  const required = ['version', 'os', 'event_kind', 'repo_id'];
  for (const k of required) {
    if (typeof body[k] !== 'string' || !body[k]) return `missing ${k}`;
  }
  if (body.version.length > 32) return 'version too long';
  if (!TELEMETRY_OS_VALUES.has(body.os)) return 'invalid os';
  if (!TELEMETRY_KINDS.has(body.event_kind)) return 'invalid event_kind';
  if (!/^[a-f0-9]{12}$/.test(body.repo_id)) return 'invalid repo_id';
  if (body.os_version != null
      && (typeof body.os_version !== 'string' || body.os_version.length > 64)) {
    return 'invalid os_version';
  }
  if (body.repo_size_bucket != null && !TELEMETRY_BUCKETS.has(body.repo_size_bucket)) {
    return 'invalid repo_size_bucket';
  }
  if (body.lang_tier_count != null
      && (!Number.isInteger(body.lang_tier_count)
          || body.lang_tier_count < 0
          || body.lang_tier_count > 100)) {
    return 'invalid lang_tier_count';
  }
  if (body.tool_name != null
      && (typeof body.tool_name !== 'string' || body.tool_name.length > 64)) {
    return 'invalid tool_name';
  }
  return null;
}

app.post('/api/telemetry', (req, res) => {
  const error = validateTelemetry(req.body);
  if (error) {
    return res.status(400).json({ error });
  }
  const entry = {
    version:          req.body.version,
    os:               req.body.os,
    os_version:       req.body.os_version || '',
    event_kind:       req.body.event_kind,
    repo_id:          req.body.repo_id,
    repo_size_bucket: req.body.repo_size_bucket || '',
    lang_tier_count:  Number.isInteger(req.body.lang_tier_count) ? req.body.lang_tier_count : null,
    tool_name:        req.body.tool_name || '',
    received_at:      new Date().toISOString(),
  };
  try {
    fs.mkdirSync(path.dirname(TELEMETRY_LOG), { recursive: true });
    fs.appendFileSync(TELEMETRY_LOG, JSON.stringify(entry) + '\n');
  } catch (err) {
    console.error(`[telemetry] append failed: ${err.message}`);
    return res.status(500).json({ error: 'log write failed' });
  }
  return res.status(204).end();
});

// API: Get waitlist (admin endpoint - requires ADMIN_KEY env var)
app.get('/api/admin/waitlist', (req, res) => {
  const adminKey = req.query.key;
  const expectedKey = process.env.ADMIN_KEY;

  if (!expectedKey) {
    return res.status(503).json({ error: 'Admin key not configured' });
  }

  if (adminKey !== expectedKey) {
    return res.status(403).json({ error: 'Unauthorized' });
  }

  res.json({
    count: waitlist.size,
    emails: Array.from(waitlist)
  });
});

// Validation evidence page
app.get('/validation', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'validation.html'));
});

// Records page
app.get(['/records', '/records/'], (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'records.html'));
});

app.get('/records.html', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'records.html'));
});

// API: validation summary (JSON)
app.get('/api/validation/summary', (req, res) => {
  res.json({
    generated: '2026-05-12',
    total_scored_runs: 100,
    stages: {
      baseline: {
        runs: 20,
        repos: 5,
        evidence_coverage_pct: 78.7,
        evidence_tag_relaxed_pct: 90.78,
        boundary_accuracy: 0.95,
        actionability: 4.0,
        hallucinations: 0,
        median_latency_s: 133.8
      },
      bgi_mcp: {
        runs: 20,
        repos: 5,
        evidence_coverage_pct: 84.9,
        evidence_tag_relaxed_pct: 94.20,
        boundary_accuracy: 1.0,
        actionability: 4.0,
        hallucinations: 0,
        median_latency_s: 66.2,
        delta_vs_baseline: { evidence_pp: +6.2, boundary: +0.05, latency_pct: -51 }
      },
      bgi_twin: {
        runs: 20,
        repos: 5,
        evidence_coverage_pct_mean: 79.9,
        evidence_coverage_pct_p04: 96.0,
        evidence_tag_relaxed_pct_mean: 94.84,
        evidence_tag_relaxed_pct_p04: 100.0,
        boundary_accuracy: 1.0,
        actionability: 4.75,
        hallucinations: 0,
        median_latency_s: 68.5,
        delta_vs_bgi_mcp: { actionability: +0.75 },
        tools: ['task_fingerprint', 'behavioral_twins', 'twin_context'],
        mcp_invocation_evidence: 'CallToolRequest confirmed in all 20 runs'
      },
      bgi_twin_replication_gpt4o: {
        runs: 20,
        repos: 5,
        evidence_coverage_pct_mean: 47.9,
        evidence_coverage_pct_p04: 49.3,
        evidence_tag_relaxed_pct_mean: 59.48,
        evidence_tag_relaxed_pct_p04: 62.72,
        boundary_accuracy: 1.0,
        actionability: 4.85,
        hallucinations: 0,
        median_latency_s: 41.55,
        model: 'azure/gpt-4o',
        notes: 'Independent-model replication of full TWIN refresh (p01-p04 x 5 repos)'
      },
      bgi_twin_replication_gemini_auto: {
        runs: 20,
        repos: 5,
        evidence_coverage_pct_mean: 62.36,
        evidence_tag_relaxed_pct_mean: 83.41,
        boundary_accuracy: 0.95,
        actionability: 4.25,
        hallucinations: 0,
        median_latency_s: 65.75,
        model: 'gemini/auto',
        notes: 'Independent-model replication on Gemini CLI auto mode; django/p02 is one genuine architectural miss (depth-first on query.py), all others correct'
      }
    },
    repos: [
      'tiangolo/fastapi',
      'django/django',
      'pydantic/pydantic-core',
      'prometheus/prometheus',
      'vercel/next.js'
    ],
    cli: 'opencode 1.14.41 / gemini CLI (auto)',
    model: 'deepseek-v4-flash + azure/gpt-4o + gemini/auto',
    rubric: 'https://github.com/ahmedxuhri/bigindexer/blob/master/validation/SCORING_RUBRIC.md',
    raw_outputs: 'https://github.com/ahmedxuhri/bigindexer/tree/master/validation/runs'
  });
});

// Serve static files (after API routes so /api/* routes are handled first)
app.use(express.static('public'));

// Catch-all: serve index.html for SPA routing
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Error handling
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

app.listen(PORT, HOST, () => {
  console.log(`🚀 Big Indexer website running on ${HOST}:${PORT}`);
  console.log(`📍 Visit http://${HOST}:${PORT}`);
});
