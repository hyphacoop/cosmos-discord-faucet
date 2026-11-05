# Cosmos Discord Faucet Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY cosmos_discord_faucet.py .
COPY chain_client.py .

# Create transactions log file
RUN touch transactions.csv

# Run the bot
CMD ["python", "-u", "cosmos_discord_faucet.py"]
