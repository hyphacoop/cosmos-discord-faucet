# Changelog

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