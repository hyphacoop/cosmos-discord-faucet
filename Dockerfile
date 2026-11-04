# Cosmos Discord Faucet Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install required system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Chain binary (override with --build-arg)
ARG BINARY_NAME=gaiad
ARG BINARY_URL=https://github.com/cosmos/gaia/releases/download/v29.1.0-rc0/gaiad-v29.1.0-rc0-linux-amd64

# Download and install the chain binary
RUN wget -q "${BINARY_URL}" -O /usr/local/bin/${BINARY_NAME} && \
    chmod +x /usr/local/bin/${BINARY_NAME} && \
    ${BINARY_NAME} version

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY cosmos_discord_faucet.py .
COPY binary_calls.py .

# Create transactions log file
RUN touch transactions.csv

# Run the bot
CMD ["python", "-u", "cosmos_discord_faucet.py"]
