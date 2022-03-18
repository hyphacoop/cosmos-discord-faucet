# Changelog

## v0.2

- The time restriction applies separately for vega and theta requests.
- Specified Python version 3.8.12 or higher.
- Added logging and error handling.

## v0.1

- First release based on [cosmos-discord-faucet](https://github.com/c29r3/cosmos-discord-faucet).
- Calls to cosmospy library were replaced with calls to gaiad (which must be initialized in the system for this software to work)
- The address prefix has been changed to `cosmos`.