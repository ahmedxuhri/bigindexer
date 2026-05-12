# Big Indexer Website

Landing page and waitlist for the Big Indexer MCP public launch.

> Current public validation lives at `https://bigindexer.com/validation`.

## Features

- 🎨 Beautiful responsive landing page
- ⏰ Waitlist signup with email validation
- 📊 Real-time waitlist status
- ✨ Modern UI with gradient theme
- 🚀 One-click deployment to Azure

## Local Development

### Prerequisites
- Node.js 18+
- npm or yarn

### Setup

```bash
npm install
npm start
```

Visit `http://localhost:3000`

### Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` with your settings:
- `PORT` - Server port (default: 3000)
- `ADMIN_KEY` - Key for accessing admin endpoints
- `NODE_ENV` - Development or production

## Deployment to Azure

### Prerequisites

- Azure CLI installed and authenticated: `az login`
- Docker installed locally
- Azure account with active subscription

### One-Command Deploy

```bash
./deploy-azure.sh
```

This script:
1. Creates a resource group
2. Sets up a container registry
3. Builds and pushes Docker image
4. Deploys to Azure App Service
5. Outputs your website URL

### Post-Deployment

After deployment, you can:

#### View Logs
```bash
az webapp log tail --name bigindexer-web --resource-group bigindexer-rg
```

#### Configure Custom Domain
```bash
az webapp config hostname add \
  --webapp-name bigindexer-web \
  --resource-group bigindexer-rg \
  --hostname bigindexer.com
```

#### Access Waitlist (Admin)
```
https://<your-app-url>/api/admin/waitlist?key=<ADMIN_KEY>
```

#### Check Waitlist Status (Public)
```
https://<your-app-url>/api/waitlist/status
```

## API Endpoints

### POST `/api/waitlist/join`
Join the waitlist.

**Request:**
```json
{
  "name": "John Doe",
  "email": "john@example.com"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Welcome to the Big Indexer waitlist!",
  "position": 42,
  "total": 42
}
```

### GET `/api/waitlist/status`
Get public waitlist status.

**Response:**
```json
{
  "waitlist_size": 42,
  "message": "People waiting for Big Indexer launch"
}
```

### GET `/api/admin/waitlist?key=<ADMIN_KEY>`
Get full waitlist (admin only).

**Response:**
```json
{
  "count": 42,
  "emails": ["user1@example.com", "user2@example.com", ...]
}
```

## Costs

**Azure Estimate (Monthly)**
- App Service Plan (B1): ~$10-15
- Container Registry: ~$5
- Storage: Minimal
- **Total**: ~$15-20/month

To reduce costs:
- Use Azure's free tier (if eligible)
- Scale down to B0 plan
- Delete when not needed: `az group delete --name bigindexer-rg`

## Customization

### Change Colors
Edit `public/index.html` - modify gradient colors in `<style>`:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Add Features
- Email notifications on signup
- Admin dashboard
- Analytics tracking
- Database persistence (Azure SQL, Cosmos DB)

## Cleanup

To remove all Azure resources:

```bash
az group delete --name bigindexer-rg --yes
```

This will delete:
- Resource group
- App Service
- Container Registry
- All associated resources

## Support

- Documentation: https://github.com/ahmedxuhri/bigindexer
- Issues: https://github.com/ahmedxuhri/bigindexer/issues
- Docs: https://github.com/ahmedxuhri/bigindexer/tree/master/docs
