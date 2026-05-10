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
