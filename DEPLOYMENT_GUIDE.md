# Phase 8 Step 3: Website and Waitlist Deployment

This directory contains the Big Indexer landing page and waitlist application, ready for deployment to Azure.

## What's Included

- **Node.js + Express server** with clean REST API
- **Beautiful responsive landing page** (HTML/CSS/JS)
- **Waitlist management** (in-memory, can be upgraded to Azure SQL/Cosmos)
- **Docker containerization** for Azure deployment
- **One-click Azure deployment script**

## Quick Start (Azure Deployment)

### Step 1: Verify Azure CLI Setup

```bash
az account show
# Should show your Azure account info
```

### Step 2: Run Deployment Script

```bash
cd website/
chmod +x deploy-azure.sh
./deploy-azure.sh
```

The script will:
1. Create resource group (no conflicts with local machine)
2. Set up container registry
3. Build Docker image
4. Push to Azure
5. Deploy to App Service
6. Output your public URL

### Step 3: Access Your Website

```
https://<generated-url>.azurewebsites.net
```

### Step 4: Configure Custom Domain (Optional)

```bash
az webapp config hostname add \
  --webapp-name bigindexer-web \
  --resource-group bigindexer-rg \
  --hostname bigindexer.com
```

## Development Locally

```bash
cd website/
npm install
npm start
# Visit http://localhost:3000
```

## API Endpoints

- `POST /api/waitlist/join` - Add email to waitlist
- `GET /api/waitlist/status` - Get public status
- `GET /api/admin/waitlist?key=...` - Admin: View all emails
- `GET /health` - Health check (for Azure)

## Environment Variables

Edit `.env` (copy from `.env.example`):
```
PORT=3000
ADMIN_KEY=your-secret-key
NODE_ENV=production
```

## Deployment Architecture

```
Local Machine (ARM Oracle VPS)
  ↓
  Docker build
  ↓
  Azure Container Registry
  ↓
  Azure App Service
  ↓
  Public: https://bigindexer.azurewebsites.net
```

**No conflicts** - all services run on Azure infrastructure.

## Costs

- **B1 App Service Plan**: $10-15/month
- **Basic Container Registry**: ~$5/month
- **Total**: ~$15-20/month

To reduce: Use free tier or delete resource group when testing.

## Cleanup

Remove everything:

```bash
az group delete --name bigindexer-rg --yes
```

## Next Steps

After deployment:

1. ✅ Website is live at Azure URL
2. 📝 Collect waitlist emails
3. 🚀 Integrate with email service for notifications
4. 📊 Add analytics (Google Analytics, Azure App Insights)
5. 💳 Eventually: Add payment for premium features

## Admin Operations

View waitlist:
```bash
curl "https://<your-url>/api/admin/waitlist?key=<ADMIN_KEY>"
```

View logs:
```bash
az webapp log tail --name bigindexer-web --resource-group bigindexer-rg
```

Restart app:
```bash
az webapp restart --name bigindexer-web --resource-group bigindexer-rg
```

