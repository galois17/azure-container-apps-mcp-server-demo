# MCP  — FastMCP + FastAPI on Azure

This project is a demonstration of the Model Context Protocol (MCP) using [FastMCP](https://github.com/fastmcp/fastmcp) and a lightweight FastAPI bridge.  

It exposes simple weather tools such as `get_forecast` through both MCP and standard HTTP endpoints, and is designed for deployment on Azure Container Apps, a serverless platform that scales to zero when idle.

---

## Features

- FastMCP Server (`mcp_weather.py`)
  - Provides MCP tools via the `stdio` transport.
  - Includes a `get_forecast(latitude, longitude)` tool that queries the U.S. National Weather Service API.

- FastAPI Bridge (`main.py`)
  - Wraps MCP tools into REST endpoints for testing or integration.
  - Example endpoint:  
    ```
    GET /get_forecast?latitude=42.36&longitude=-71.06
    ```

- Cloud Deployment
  - Containerized with `uv` and Python 3.11.
  - Deployable to Azure Container Apps with serverless autoscaling.

---

## Local Development

```bash
# Install dependencies
uv venv
uv sync

uv run python main.py
```
The open in your browser:
```bash
http://localhost:8000/get_forecast?latitude=42.36&longitude=-71.06
```

```bash
docker build -t test-mcp-app .
docker run -p 8000:8000 test-mcp-app
```

Test the endpoint:
```bash
curl "http://localhost:8000/get_forecast?latitude=42.36&longitude=-71.06"
```

## Deploy to Azure (Serverless)

```bash
# Login to Azure
az login

# Create a resource group
az group create --name TestResourceGroup --location eastus2

# Create a container registry (Basic tier is cheapest)
az acr create \
  --name mcpdemoacr \
  --resource-group TestResourceGroup \
  --sku Basic

# Log in to the container registry
az acr login --name mcpdemoacr

# Build the Docker image locally
docker build -t test-mcp-app .

# Tag and push the image to ACR
docker tag test-mcp-app mcpdemoacr.azurecr.io/test-mcp-app:v1
docker push mcpdemoacr.azurecr.io/test-mcp-app:v1

# Create a Container Apps environment (serverless)
az containerapp env create \
  --name MCPDemoEnv \
  --resource-group TestResourceGroup \
  --location eastus2

# Create the Container App (serverless, scales to zero)
az containerapp create \
  --name test-mcp-app \
  --resource-group TestResourceGroup \
  --environment MCPDemoEnv \
  --image mcpdemoacr.azurecr.io/test-mcp-app:v1 \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --registry-server mcpdemoacr.azurecr.io \
  --registry-username $(az acr credential show --name mcpdemoacr --query "username" -o tsv) \
  --registry-password $(az acr credential show --name mcpdemoacr --query "passwords[0].value" -o tsv)


```

Retrieve your live app URL:

```bash
az containerapp show \
  --name test-mcp-app \
  --resource-group TestResourceGroup \
  --query "properties.configuration.ingress.fqdn" -o tsv

```