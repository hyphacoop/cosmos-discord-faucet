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

- python 3.8.12+
- gaia v6.0.3+
- Initialized gaia instance
- Faucet keys in gaia keyring

## Installation

1. Python dependencies:
   
```
cosmos-discord-faucet$ python -m venv .env
cosmos-discord-faucet$ source .env/bin/activate
cosmos-discord-faucet$ pip install -r requirements.txt
```

1. [Create a Discord token](https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token)
2. Add the bot token to `config.toml`
3. Modify the nodes, faucet addresses, amount to send, etc. in `config.toml`

## Usage

This bot can be run stand-alone (mostly for testing), or as a service.

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
`$request [cosmos address] theta|devnet`
   - The response will include a ✅ and the transaction hash if it was successful.

2. Request the faucet and node status:  
`$faucet_status theta|devnet`

3. Request the faucet address:  
`$faucet_address theta|devnet`

4. Request information for a specific transaction:  
`$tx_info [transaction hash ID] theta|devnet`

5. Request the address balance:  
`$balance [cosmos address] theta|devnet`  


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
