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
- gRPC access to a node for each chain (port 9090 by default)
- the mnemonic of the faucet key for each chain

No chain binary is needed: the bot builds, signs and broadcasts transactions itself using [cosmpy](https://github.com/fetchai/cosmpy).

## Installation

1. Python dependencies:
   
```
cosmos-discord-faucet$ python -m venv .env
cosmos-discord-faucet$ source .env/bin/activate
cosmos-discord-faucet$ pip install -r requirements.txt
```

1. Set up the Discord app:
   1. Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications) and copy the bot token.
   2. Leave **Message Content Intent** turned off. The bot only uses slash commands, so it doesn't need any privileged intents.
   3. Invite the bot to your server with the `bot` and `applications.commands` scopes (OAuth2 → URL Generator).
2. Copy the example config: `cp config.toml.example config.toml`
3. Add the bot token to `config.toml`
4. Modify the gRPC endpoints, faucet addresses, amount to send, etc. in `config.toml`
5. For each chain, save the faucet key's mnemonic in a file and set `mnemonic_file` to its path:

```
echo "word1 word2 ... word24" > ~/.faucet/chain-1.mnemonic
chmod 600 ~/.faucet/chain-1.mnemonic
```

The bot derives the key with the standard Cosmos HD path (`m/44'/118'/0'/0/0`, the `gaiad keys add` default) and exits at startup if the derived address doesn't match `faucet_address`.

### Restricting channels

By default the commands can be used in any channel the bot can see. To limit them, go to **Server Settings → Integrations → *your bot*** and set which channels (and roles) can use each command.

## Usage

This bot can be run stand-alone (mostly for testing), as a service, or in a Docker container.

### Docker

#### Building the Docker Image

```bash
docker build -t cosmos-discord-faucet .
```

The image contains the Python 3.11 runtime and the dependencies from requirements.txt. No chain binary is needed.

#### Running the Docker Container

To run the container with your local configuration, faucet mnemonics, and persistent transaction logs:

```bash
docker run -d \
  --name cosmos-faucet \
  --restart unless-stopped \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  -v $(pwd)/transactions.csv:/app/transactions.csv \
  -v $HOME/.faucet/chain-1.mnemonic:/secrets/chain-1.mnemonic:ro \
  cosmos-discord-faucet
```

**Restarts:**
`--restart unless-stopped` brings the container back after a crash or a reboot, unless you stopped it with `docker stop`. Docker itself must start at boot (`sudo systemctl enable docker`; most installs already do this). To add the policy to an existing container without recreating it, run `docker update --restart unless-stopped cosmos-faucet`.

If the config is invalid (for example a missing mnemonic file), the bot exits at startup and Docker keeps retrying with increasing delays. Check `docker logs cosmos-faucet` if the bot doesn't come online.

**Volume Mounts:**
- `-v $(pwd)/config.toml:/app/config.toml:ro` - Mounts your config file as read-only
- `-v $(pwd)/transactions.csv:/app/transactions.csv` - Persists transaction logs to your host
- `-v $HOME/.faucet/chain-1.mnemonic:/secrets/chain-1.mnemonic:ro` - Mounts the faucet mnemonic as read-only. Add one mount per chain.

**Mnemonic paths:**
The bot reads `mnemonic_file` from inside the container, so it must be the container path (the right side of the `-v` mount), not the path on your host. The container runs as root, so `~` in `mnemonic_file` expands to `/root`. If the path doesn't exist in the container, the bot exits at startup with `Could not set up chain client: ... No such file or directory`.

There are two ways to set this up:

1. Mount each file under `/secrets` and use those paths in `config.toml` (as in the example above):
   ```bash
   -v $HOME/.faucet/chain-1.mnemonic:/secrets/chain-1.mnemonic:ro \
   -v $HOME/.faucet/chain-2.mnemonic:/secrets/chain-2.mnemonic:ro \
   ```
   ```toml
   [chains.chain-1]
   mnemonic_file = "/secrets/chain-1.mnemonic"
   [chains.chain-2]
   mnemonic_file = "/secrets/chain-2.mnemonic"
   ```
2. Keep `mnemonic_file = "~/.faucet/chain-1.mnemonic"` (as in `config.toml.example`) and mount the whole folder at `/root/.faucet`, so the same `config.toml` works with and without Docker:
   ```bash
   -v $HOME/.faucet:/root/.faucet:ro \
   ```

**Networking:**
If the node runs on the Docker host (for example `grpc_url = "grpc+http://localhost:9090"`), `localhost` inside the container doesn't reach it. Either add `--network host` to `docker run` (Linux), or set `grpc_url` to `grpc+http://host.docker.internal:9090`. On Linux, the second option also needs `--add-host=host.docker.internal:host-gateway`.

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

The bot uses slash commands. Discord can take up to an hour to show them after the bot first starts, or after a command changes.

1. Request tokens through the faucet:  
`/request address:<cosmos address>` (when one chain is configured)  
`/request chain:<chain> address:<cosmos address>` (when several chains are configured)
   - With several chains, pick the chain from the list. To give users the address-only command for each chain, run one bot per chain, each with its own config and Discord app.
   - The response will include a ✅ and the transaction link or hash if it was successful.
   - If the request is rejected (invalid address, cooldown, or daily cap), the reply is only visible to the person who made the request.

2. Show usage and the supported chains (only visible to you):  
`/help`

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
- The cosmospy library calls were replaced by calls to `gaiad` to avoid deprecated endpoints and messages, and later by in-process signing with cosmpy.
- The address prefix has been switched to `cosmos`.
