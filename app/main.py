from fastapi import FastAPI

app = FastAPI(
    title="Clariti TMS",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
