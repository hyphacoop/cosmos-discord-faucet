# cosmos-discord-faucet
A Discord bot for dispensing testnet tokens.

## Requirements

- python 3.8.12+
- gaia v6.0.3+
- Faucet keys in gaia keyring 

## Installation

1. Install dependencies:
   
```
cosmos-discord-faucet$ python -m venv .env
cosmos-discord-faucet$ source .env/bin/activate
cosmos-discord-faucet$ pip install -r requirements.txt
```

2. [Create Discord token](https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token) and save its token.
3. Add the bot token to `config.toml`.
4. Modify the nodes, faucet addresses, and amount to send in `config.toml` .

## Usage

This bot can be run stand-alone (mostly for testing), or as a service.

### Stand-alone

`python cosmos_discord_faucet.py`

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
`$request [cosmos address] vega|theta`
- A ✅ means the transaction was successful

2. Request the faucet and node status:  
`$faucet_status vega|theta`

3. Request the faucet address:  
`$faucet_address vega|theta`

4. Request information for a specific transaction:  
`$tx_info [transaction hash ID] vega|theta`

5. Request the address balance:  
`$balance [cosmos address] vega|theta`  


## Acknowledgements

This repo is based on [cosmos-discord-faucet](https://github.com/c29r3/cosmos-discord-faucet):
- The cosmospy library calls have been replaced by calls to `gaiad` to avoid deprecated endpoints and messages.
- The address prefix has been switched to `cosmos`.
