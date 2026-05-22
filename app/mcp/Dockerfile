# Distributable MCP server image. Runs `clariti-mcp` on stdio.
#
# Build from the repo root so the build context includes pyproject.toml
# and the app/ package:
#
#   docker build -f app/mcp/Dockerfile -t clariti/mcp:latest .
#
# Run via `docker run -i` (stdio attached) with the API config wired in:
#
#   docker run -i --rm \
#     -e CLARITI_API_URL=https://tms.example.com \
#     -e CLARITI_API_KEY=$CLARITI_API_KEY \
#     clariti/mcp:latest

FROM python:3.13-slim

WORKDIR /app

# Install build deps for any wheels that need them. Kept minimal so the
# final layer is small; the MCP server itself only needs httpx + mcp.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY cli ./cli

RUN pip install --no-cache-dir .

# stdio transport — no port exposed. Container is invoked with `-i`
# so the agent can write to stdin / read from stdout.
ENTRYPOINT ["clariti-mcp"]
