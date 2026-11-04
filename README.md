# cosmos-discord-faucet
A Discord bot for dispensing testnet tokens.

## Features

- Responds to requests for tokens on multiple testnets
- Response includes a link to the transaction detail in the appropriate block explorer
- Limits the tokens a user can get within a time period for a given testnet
- Limits the tokens an address can get within a time period for a given testnet
- Daily cap for each testnet token
- Requests are saved in local csv file: date, cosmos address, amount, and testnet
- Errors are logged to systemd journal

## Requirements

- python 3.11.12+
- cosmos binary avaliable in path
- faucet key in test keyring

## Installation

1. Python dependencies:
   
```
cosmos-discord-faucet$ python -m venv .env
cosmos-discord-faucet$ source .env/bin/activate
cosmos-discord-faucet$ pip install -r requirements.txt
```

1. [Create a Discord token](https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token)
2. Copy the example config: `cp config.toml.example config.toml`
3. Add the bot token to `config.toml`
4. Modify the nodes, faucet addresses, amount to send, etc. in `config.toml`

## Usage

This bot can be run stand-alone (mostly for testing), as a service, or in a Docker container.

### Docker

#### Building the Docker Image

```bash
docker build -t cosmos-discord-faucet .
```

The Dockerfile includes:
- Python 3.11 runtime
- Automatic download of the chain binary (gaiad v25.3.2 by default)
- All Python dependencies from requirements.txt

To use a different binary or version, pass build arguments:
- `BINARY_NAME` (default: `gaiad`): the name the binary is installed as. It must match the `binary` setting in `config.toml`.
- `BINARY_URL` (default: the gaiad v25.3.2 linux-amd64 release): where to download the binary from

```bash
docker build -t cosmos-discord-faucet \
  --build-arg BINARY_NAME=gaiad \
  --build-arg BINARY_URL=https://github.com/cosmos/gaia/releases/download/v25.3.2/gaiad-v25.3.2-linux-amd64 \
  .
```

#### Running the Docker Container

To run the container with your local configuration, faucet keyring, and persistent transaction logs:

```bash
docker run -d \
  --name cosmos-faucet \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  -v $(pwd)/transactions.csv:/app/transactions.csv \
  -v $HOME/.gaia/keyring-test:/root/.gaia/keyring-test:ro \
  cosmos-discord-faucet
```

**Volume Mounts:**
- `-v $(pwd)/config.toml:/app/config.toml:ro` - Mounts your config file as read-only
- `-v $(pwd)/transactions.csv:/app/transactions.csv` - Persists transaction logs to your host
- `-v $HOME/.gaia/keyring-test:/root/.gaia/keyring-test:ro` - Mounts the faucet keyring as read-only so the binary can sign transactions

**Keyring:**
The bot signs transfers with `--keyring-backend test --home <home_folder>`, so the faucet key must be available at `<home_folder>/keyring-test` inside the container.
- The container runs as root, so a `home_folder` of `~/.gaia` resolves to `/root/.gaia`. Add one keyring mount per chain, matching each chain's `home_folder`.
- The key must already exist on the host, for example from `gaiad keys add faucet --keyring-backend test`. Its address must match `faucet_address`.
- Mount only the `keyring-test` directory, not the whole home folder, so node data and validator keys stay out of the container. The binary may write `config/client.toml` into the home folder on first use. That write goes to the container's writable layer, which is fine.

To check that the container can see the key:

```bash
docker run --rm \
  -v $HOME/.gaia/keyring-test:/root/.gaia/keyring-test:ro \
  cosmos-discord-faucet \
  gaiad keys list --home /root/.gaia --keyring-backend test
```

**Networking:**
If the node runs on the Docker host (for example `node_url = "http://localhost:26657"`), `localhost` inside the container doesn't reach it. Either add `--network host` to `docker run` (Linux), or set `node_url` to `http://host.docker.internal:26657`. On Linux, the second option also needs `--add-host=host.docker.internal:host-gateway`.

**Container Management:**
```bash
# View logs
docker logs -f cosmos-faucet

# Stop the container
docker stop cosmos-faucet

# Restart the container
docker restart cosmos-faucet

# Remove the container
docker rm cosmos-faucet
```

### Stand-alone

```
python cosmos_discord_faucet.py
```

- This can be run inside a `tmux` session.

### Service

1. Modify the `cosmos-discord-faucet.service` file as appropriate.
2. Make a copy of `cosmos-discord-faucet.service` or create a link to it in `/etc/systemd/system/`.
3. Enable and start the service:
```
systemctl daemon-reload
systemctl enable cosmos-discord-faucet.service
systemctl start cosmos-discord-faucet.service
systemctl status cosmos-discord-faucet.service
```

## Discord Commands

1. Request tokens through the faucet:  
`$request [chain] [cosmos address]`
   - The response will include a ✅ and the transaction hash if it was successful.

2. Request the faucet and node status:  
`$faucet_status [chain]`

3. Request the faucet address:  
`$faucet_address [chain]`

4. Request information for a specific transaction:  
`$tx_info [chain] [transaction hash ID]`

5. Request the address balance:  
`$balance [chain] [cosmos address]`  


## Analytics

The `transactions.csv` file can be parsed using `cosmos_faucet_analytics.py` to output faucet usage analytics to a Node Exporter-compatible file.

### Analytics Usage

The analytics script can be run stand-alone (mostly for testing), or as a service.

- Modify the log paths and logging period in `config_analytics.toml` as required. 

### Analytics Stand-alone

```
python cosmos_faucet_analytics.py
```

- This can be run inside a `tmux` session.

### Analytics Service

1. Modify the `cosmos-faucet-analytics.service` file as appropriate.
2. Make a copy of `cosmos-faucet-analytics.service` or create a link to it in `/etc/systemd/system/`.
3. Enable and start the service:
```
systemctl daemon-reload
systemctl enable cosmos-faucet-analytics.service
systemctl start cosmos-faucet-analytics.service
systemctl status cosmos-faucet-analytics.service
```

## Acknowledgements

This repo is based on [cosmos-discord-faucet](https://github.com/c29r3/cosmos-discord-faucet):
- The cosmospy library calls have been replaced by calls to `gaiad` to avoid deprecated endpoints and messages.
- The address prefix has been switched to `cosmos`.
