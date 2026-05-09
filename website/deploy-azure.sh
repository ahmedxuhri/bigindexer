#!/bin/bash
# Deploy Big Indexer Website to Azure
# This script creates a fresh Azure deployment (no conflicts with local machine)

set -e

# Configuration
RESOURCE_GROUP="bigindexer-rg"
LOCATION="eastus"
REGISTRY_NAME="bigindexerregistry"
APP_NAME="bigindexer-web"
APP_PLAN="bigindexer-plan"
CONTAINER_IMAGE="bigindexer-web:latest"

echo "=========================================="
echo "Big Indexer Website - Azure Deployment"
echo "=========================================="
echo ""

# Check Azure CLI
if ! command -v az &> /dev/null; then
  echo "❌ Azure CLI not found. Please install: https://docs.microsoft.com/cli/azure/install-azure-cli"
  exit 1
fi

# Check if already logged in
if ! az account show &> /dev/null; then
  echo "⚠️  Not logged into Azure. Run 'az login' first."
  exit 1
fi

ACCOUNT=$(az account show --query "user.name" -o tsv)
echo "✓ Logged in as: $ACCOUNT"
echo ""

# Step 1: Create Resource Group
echo "[1/5] Creating resource group: $RESOURCE_GROUP..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

echo "✓ Resource group created"
echo ""

# Step 2: Create Container Registry
echo "[2/5] Creating container registry: $REGISTRY_NAME..."
REGISTRY_URL=$(az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$REGISTRY_NAME" \
  --sku Basic \
  --query loginServer \
  -o tsv 2>/dev/null || az acr show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$REGISTRY_NAME" \
  --query loginServer \
  -o tsv)

echo "✓ Container registry: $REGISTRY_URL"
echo ""

# Step 3: Build and push Docker image
echo "[3/5] Building Docker image..."
cd "$(dirname "$0")"

# Build image
docker build -t "$CONTAINER_IMAGE" .

# Tag for registry
docker tag "$CONTAINER_IMAGE" "$REGISTRY_URL/$CONTAINER_IMAGE"

echo "✓ Docker image built: $CONTAINER_IMAGE"
echo ""

echo "[3b/5] Logging into registry and pushing image..."
az acr login --name "$REGISTRY_NAME"

# Push to registry
docker push "$REGISTRY_URL/$CONTAINER_IMAGE"

echo "✓ Image pushed to registry"
echo ""

# Step 4: Create App Service Plan
echo "[4/5] Creating App Service plan: $APP_PLAN..."
az appservice plan create \
  --name "$APP_PLAN" \
  --resource-group "$RESOURCE_GROUP" \
  --sku B1 \
  --is-linux \
  --output none

echo "✓ App Service plan created"
echo ""

# Step 5: Create Web App
echo "[5/5] Creating Web App: $APP_NAME..."
az webapp create \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$APP_PLAN" \
  --name "$APP_NAME" \
  --deployment-container-image-name "$REGISTRY_URL/$CONTAINER_IMAGE" \
  --output none 2>/dev/null || true

# Configure container settings
az webapp config container set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --docker-custom-image-name "$REGISTRY_URL/$CONTAINER_IMAGE" \
  --docker-registry-server-url "https://$REGISTRY_URL" \
  --output none

# Enable continuous deployment from registry
az webapp deployment container config \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --enable-cd true \
  --output none

# Set app settings
az webapp config appsettings set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    WEBSITES_ENABLE_APP_SERVICE_STORAGE=false \
    PORT=3000 \
  --output none

echo "✓ Web App created and configured"
echo ""

# Get app URL
APP_URL=$(az webapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --query defaultHostName \
  -o tsv)

echo "=========================================="
echo "✨ Deployment Complete!"
echo "=========================================="
echo ""
echo "Website URL: https://$APP_URL"
echo ""
echo "Next steps:"
echo "1. Visit https://$APP_URL to test"
echo "2. Configure custom domain (bigindexer.com):"
echo "   az webapp config hostname add --webapp-name $APP_NAME --resource-group $RESOURCE_GROUP --hostname bigindexer.com"
echo "3. Configure SSL certificate (recommended)"
echo "4. View logs: az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "Admin: View waitlist at https://$APP_URL/api/admin/waitlist?key=demo-key"
echo "(Change ADMIN_KEY in production)"
echo ""
