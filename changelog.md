# Changelog

## v0.9.0

- [**BREAKING CHANGE**] The bot now uses Discord slash commands and no longer needs the Message Content Intent.
  - `$request` is now `/request address:<address>` when one chain is configured, or `/request chain:<chain> address:<address>` with several chains. `$help` is now `/help`. Rejections are only visible to the requester.
  - `$balance`, `$tx_info`, `$faucet_status` and `$faucet_address` have been removed.
  - `channels_to_listen` has been removed. Use Server Settings → Integrations in Discord to restrict channels.
  - Invite the bot with the `applications.commands` scope.
- [**BREAKING CHANGE**] Transactions are built, signed and broadcast in-process with [cosmpy](https://github.com/fetchai/cosmpy); the chain binary is no longer needed.
  - Per-chain config: `binary`, `home_folder` and `node_url` have been removed. `grpc_url` and `mnemonic_file` are required, and `gas_limit` is optional (default `200000`).
  - The bot exits at startup if a mnemonic doesn't derive the configured `faucet_address`.
  - The Docker image no longer downloads a chain binary, and the `BINARY_NAME`/`BINARY_URL` build arguments have been removed.
- Fixed per-chain cooldowns and locks being looked up by chain ID instead of the config table name.

## v0.8.0

- [**BREAKING CHANGE**] Updated `discord.py` to `v2.3.2` ([#35](https://github.com/hyphacoop/cosmos-discord-faucet/pull/35))
  - Please note that the intents setting must be configured accordingly for the Discord server in order for messages to be read by the bot.
- A per-chain binary can be now specified in config.toml.

## v0.7.0

- Multi chain support
- Rename metrics to align with Prometheus best practices

## v0.6.2

- Incorrect chain names are ignored.

## v0.6.1

- Gaia calls are made with the '--output=json' flag.
- IBC denoms are now displayed in the '$balance' message reply. 

## v0.6.0

- Added analytics logic.
- The resulting log file is compatible with Node Exporter.

## v0.5

- The transactions log includes the faucet balance.
- The transactions log uses the Python ISO date-time format.

## v0.4

- The `$balance` command now responds with all the available denoms in an account.
- The `$faucet_status` command no longer includes the faucet balance.

## v0.3

- The Vega testnet has gone offline.
- Removed vega testnet from `config.toml`.
- If a user mentions vega in a message starting with '$', reply with a notification.

## v0.2

- The time restriction applies separately for vega, theta, and devnet requests.
- Specified Python version 3.8.12 or higher.
- Added link to transaction details on the token request response.
- Added logging and error handling.
- Added daily caps per faucet.
- Separate send amounts and transaction fees per faucet.

## v0.1

- First release based on [cosmos-discord-faucet](https://github.com/c29r3/cosmos-discord-faucet).
- Calls to cosmospy library were replaced with calls to gaiad (which must be initialized in the system for this software to work)
- The address prefix has been changed to `cosmos`.