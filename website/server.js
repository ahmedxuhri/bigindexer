const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const path = require('path');


const app = express();
const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static('public'));

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

// API: Get waitlist (admin endpoint - in production, require auth)
app.get('/api/admin/waitlist', (req, res) => {
  const adminKey = req.query.key;
  const expectedKey = process.env.ADMIN_KEY || 'demo-key';

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

// API: validation summary (JSON)
app.get('/api/validation/summary', (req, res) => {
  res.json({
    generated: '2026-05-11',
    total_scored_runs: 60,
    stages: {
      baseline: {
        runs: 20,
        repos: 5,
        evidence_coverage_pct: 78.7,
        boundary_accuracy: 0.95,
        actionability: 4.0,
        hallucinations: 0,
        median_latency_s: 133.8
      },
      bgi_mcp: {
        runs: 20,
        repos: 5,
        evidence_coverage_pct: 84.9,
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
        boundary_accuracy: 1.0,
        actionability: 4.75,
        hallucinations: 0,
        median_latency_s: 68.5,
        delta_vs_bgi_mcp: { actionability: +0.75 },
        tools: ['task_fingerprint', 'behavioral_twins', 'twin_context'],
        mcp_invocation_evidence: 'CallToolRequest confirmed in all 20 runs'
      }
    },
    repos: [
      'tiangolo/fastapi',
      'django/django',
      'pydantic/pydantic-core',
      'prometheus/prometheus',
      'vercel/next.js'
    ],
    cli: 'opencode 1.14.41',
    model: 'deepseek-v4-flash',
    rubric: 'https://github.com/ahmedxuhri/bigindexer/blob/master/validation/SCORING_RUBRIC.md',
    raw_outputs: 'https://github.com/ahmedxuhri/bigindexer/tree/master/validation/runs'
  });
});

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
