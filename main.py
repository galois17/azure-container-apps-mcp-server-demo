import logging
from fastapi import FastAPI, HTTPException
from fastmcp import Client as StdioClient  # Using stdio transport
import uvicorn

logger = logging.getLogger("mcp_bridge")
logging.basicConfig(level=logging.INFO)

MCP_SERVER_PATH = "mcp_weather.py"

app = FastAPI(title="MCP FastAPI Bridge (stdio)")

async def call_mcp_tool(tool_name: str, args: dict):
    """
    Launches the MCP server using stdio and calls a tool.
    """
    logger.info(f"Launching MCP via stdio to call tool: {tool_name}")
    
    try:
        async with StdioClient(MCP_SERVER_PATH) as client:
            print("Connecting to weather MCP...\n")
            
            result = await client.call_tool("get_forecast", args)
            print(f"Result: {result}")
            return result
    except Exception:
        logger.exception("Error calling MCP tool")
        raise

@app.get("/get_forecast")
async def get_forecast(latitude: float, longitude: float):
    """
    FastAPI endpoint that proxies to an MCP tool via stdio.
    """
    try:
        result = await call_mcp_tool(
            "get_forecast", {"latitude": latitude, "longitude": longitude}
        )
        return {"tool": "get_forecast", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"status": "MCP stdio bridge running"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)