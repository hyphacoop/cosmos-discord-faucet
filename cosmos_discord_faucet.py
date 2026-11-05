"""
Sets up a Discord bot that dispenses testnet tokens through slash commands

"""

import asyncio
import time
import datetime
import logging
import os
import sys
from typing import Optional, Tuple

import aiofiles as aiof
import discord
import toml
from discord import app_commands

from chain_client import ChainClient, ChainError

# Turn Down Discord Logging
disc_log = logging.getLogger('discord')
disc_log.setLevel(logging.CRITICAL)

# Configure Logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# Global variables (will be initialized by load_config)
TX_LOG_PATH = None
REQUEST_TIMEOUT = None
DISCORD_TOKEN = None
# Chain configs keyed by table name in config.toml. load_config adds runtime
# state to each: 'key', 'client' (ChainClient), 'requests' (cooldowns),
# 'active_day' and 'day_tally'.
chains = None

APPROVE_EMOJI = '✅'
REJECT_EMOJI = '🚫'
GENERIC_ERROR_REPLY = '❗ request could not be processed'

# Constants
TWO_HOURS_IN_MINUTES = 120  # Threshold for displaying hours vs minutes
MAX_CHAIN_CHOICES = 25  # Discord limit on slash command choices
MAX_ADDRESS_LENGTH = 128


def load_config(config_path: str = 'config.toml') -> None:
    """
    Load configuration from TOML file and initialize global variables
    """
    global TX_LOG_PATH, REQUEST_TIMEOUT, DISCORD_TOKEN, chains

    try:
        config = toml.load(config_path)
    except FileNotFoundError:
        logging.critical('Config file not found: %s', config_path)
        sys.exit(1)
    except toml.TomlDecodeError as ex:
        logging.critical('Failed to parse config file: %s', ex)
        sys.exit(1)

    try:
        TX_LOG_PATH = config['transactions_log']
        REQUEST_TIMEOUT = int(config['discord']['request_timeout'])
        DISCORD_TOKEN = str(config['discord']['bot_token'])
        chains = config['chains']
        if len(chains) > MAX_CHAIN_CHOICES:
            logging.critical('At most %d chains are supported, found %d',
                             MAX_CHAIN_CHOICES, len(chains))
            sys.exit(1)
        for key, chain in chains.items():
            chain['key'] = key
            chain['mnemonic_file'] = os.path.expanduser(chain['mnemonic_file'])
            chain['active_day'] = datetime.datetime.today().date()
            chain['day_tally'] = 0
            chain['requests'] = {}
            chain['client'] = ChainClient(chain)
            logging.info('Loaded chain %s (%s) with faucet address %s',
                         key, chain['chain_id'], chain['client'].address)
    except KeyError as key:
        logging.critical('Key could not be found in config: %s', key)
        sys.exit(1)
    except (OSError, ValueError) as ex:
        logging.critical('Could not set up chain client: %s', ex)
        sys.exit(1)


def build_help_message() -> str:
    """
    Build the /help reply from the configured chains
    """
    example_chain = next(iter(chains.values()))
    example_address = f'{example_chain["prefix"]}1...'
    if len(chains) == 1:
        usage = '`/request address:<address>`'
        example = f'/request address:{example_address}'
    else:
        usage = '`/request chain:<chain> address:<address>`'
        example = f'/request chain:{example_chain["key"]} address:{example_address}'
    help_msg = '**Request tokens**\n' \
        f'{usage}\n' \
        f'You can request tokens once every {int(REQUEST_TIMEOUT / 3600)} hours per chain.\n\n' \
        f'Example: `{example}`\n\n' \
        '**Supported chains**\n'
    for key, data in chains.items():
        help_msg += f'* `{key}` (chain ID `{data["chain_id"]}`)\n'
        help_msg += f'  * {data["description"]}\n' if data.get('description') else ''
        help_msg += f'  * {data["website"]}\n' if data.get('website') else ''
    return help_msg


async def save_transaction_statistics(transaction: str) -> None:
    """
    Transaction strings are already comma-separated
    """
    async with aiof.open(TX_LOG_PATH, 'a') as csv_file:
        await csv_file.write(f'{transaction}\n')
        await csv_file.flush()


async def get_faucet_balance(chain: dict) -> Optional[str]:
    """
    Returns the faucet balance for the chain's denom, or None if the query fails
    """
    try:
        amount = await asyncio.to_thread(chain['client'].get_faucet_balance)
    except ChainError as ex:
        logging.error('Faucet balance query failed for %s: %s', chain['key'], ex)
        return None
    return f'{amount}{chain["denom"]}'


def format_timeout_message(check_time: float, message_timestamp: float) -> str:
    """
    Generate a timeout message based on the time remaining
    """
    seconds_left = check_time - message_timestamp
    minutes_left = seconds_left / 60
    if minutes_left > TWO_HOURS_IN_MINUTES:
        wait_time = f'{int(minutes_left/60)} hours'
    else:
        wait_time = f'{int(minutes_left)} minutes'
    timeout_in_hours = int(REQUEST_TIMEOUT / 60 / 60)
    return f'{REJECT_EMOJI} You can request coins no more than once every' \
           f' {timeout_in_hours} hours for the same chain, ' \
           f'please try again in ' \
           f'{wait_time}'


def _check_single_time_limit(entity_id, chain: dict, message_timestamp: float) -> Tuple[bool, Optional[str]]:
    """
    Helper function to check if a single entity (user or address) is time-blocked.
    Returns (is_blocked, reply_message)
    """
    chain_requests = chain['requests']

    if entity_id not in chain_requests:
        return False, None

    check_time = chain_requests[entity_id]['next_request']
    if check_time > message_timestamp:
        reply = format_timeout_message(check_time, message_timestamp)
        return True, reply

    # Time limit expired, remove the entry
    del chain_requests[entity_id]
    return False, None


def _register_request_limits(requester, address: str, chain: dict, message_timestamp: float) -> None:
    """
    Register time limits for both requester and address
    """
    chain_requests = chain['requests']
    chain_requests[requester] = {'next_request': message_timestamp + REQUEST_TIMEOUT}
    chain_requests[address] = {'next_request': message_timestamp + REQUEST_TIMEOUT}


def check_time_limits(requester, address: str, chain: dict) -> Tuple[bool, Optional[str]]:
    """
    Returns True, None if the given requester and address are not time-blocked for the given chain
    Returns False, reply if either of them is still on time-out; msg is the reply to the requester
    """
    message_timestamp = time.time()

    # Check user allowance
    is_blocked, reply = _check_single_time_limit(requester, chain, message_timestamp)
    if is_blocked:
        return False, reply

    # Check address allowance
    is_blocked, reply = _check_single_time_limit(address, chain, message_timestamp)
    if is_blocked:
        return False, reply

    # Register time limits for this request
    _register_request_limits(requester, address, chain, message_timestamp)
    return True, None


def check_daily_cap(chain: dict, delta: int) -> bool:
    """
    Returns True if the faucet has not reached the daily cap
    Returns False otherwise
    Does not modify state - only checks
    """
    # Check date
    today = datetime.datetime.today().date()
    if today > chain['active_day']:
        # The date has changed, would reset the tally
        return True

    # Check tally
    if chain['day_tally'] + delta > int(chain['daily_cap']):
        return False

    return True


def increment_daily_tally(chain: dict, delta: int) -> None:
    """
    Increment or reset the daily tally
    Must follow check_daily_cap with no await in between (see reserve_request)
    """
    today = datetime.datetime.today().date()
    if today > chain['active_day']:
        # The date has changed, reset the tally
        chain['active_day'] = today
        chain['day_tally'] = delta
    else:
        chain['day_tally'] += delta


async def record_transfer(requester, address: str, chain: dict, transfer: str) -> str:
    """
    Log a completed transfer to the transaction log and return the reply message
    """
    logging.info('%s requested tokens for %s in %s',
                 requester, address, chain['chain_id'])
    now = datetime.datetime.now()

    # Get faucet balance and save to transaction log
    balance = await get_faucet_balance(chain)
    await save_transaction_statistics(f'{now.isoformat(timespec="seconds")},'
                                      f'{chain["chain_id"]},{address},'
                                      f'{chain["amount_to_send"] + chain["denom"]},'
                                      f'{transfer},'
                                      f'{balance}')

    # Format reply with block explorer link or hash
    if chain["block_explorer_tx"]:
        return f'{APPROVE_EMOJI}  <{chain["block_explorer_tx"]}{transfer}>'
    return f'{APPROVE_EMOJI} Hash ID: {transfer}'


def reserve_request(requester, address: str, chain: dict) -> Optional[str]:
    """
    Run the quick checks for a token request and, if they pass, reserve the
    cooldowns and daily tally for it.
    Returns None if the request was reserved, otherwise the rejection reply.

    This must stay synchronous (no awaits), so the check-and-reserve is atomic
    on the event loop without waiting for a transfer in progress, which can
    take longer than Discord's 3 second response window.
    """
    # Check address (local bech32 decode, no node call)
    reason = chain['client'].validate_address(address)
    if reason is not None:
        return f'❗ {reason}'

    delta = int(chain["amount_to_send"])

    # Check whether the faucet has reached the daily cap
    if not check_daily_cap(chain=chain, delta=delta):
        logging.info('%s requested tokens for %s in %s '
                     'but the daily cap has been reached',
                     requester, address, chain['chain_id'])
        return 'Sorry, the daily cap for this faucet has been reached'

    # Check whether user or address have received tokens on this chain;
    # registers the cooldowns if not
    approved, reply = check_time_limits(
        requester=requester.id, address=address, chain=chain)
    if not approved:
        logging.info('%s requested tokens for %s in %s and was rejected',
                     requester, address, chain['chain_id'])
        return reply

    # Increment the daily tally now that we're committed to the request
    increment_daily_tally(chain, delta)
    return None


def release_request(requester, address: str, chain: dict) -> None:
    """
    Undo a reservation made by reserve_request
    """
    chain['requests'].pop(requester.id, None)
    chain['requests'].pop(address, None)
    chain['day_tally'] -= int(chain["amount_to_send"])


async def send_ephemeral_followup(interaction: discord.Interaction, message: str) -> None:
    """
    Send a message only the user can see after the response was deferred.
    A public deferral can't be turned ephemeral, so remove the public
    "thinking" message first.
    """
    try:
        await interaction.delete_original_response()
    except discord.HTTPException as ex:
        logging.warning('Could not delete deferred response: %s', ex)
    await interaction.followup.send(message, ephemeral=True)


async def handle_request(interaction: discord.Interaction, chain: dict, address: str) -> None:
    """
    Handle a /request interaction for the given chain
    """
    requester = interaction.user
    address = address.strip()

    # Quick checks: rejections are only shown to the requester
    rejection = reserve_request(requester, address, chain)
    if rejection is not None:
        await interaction.response.send_message(rejection, ephemeral=True)
        return

    # The reservation is released if anything fails before the tokens are sent
    try:
        # Sending can take longer than the 3 seconds Discord allows for a reply
        await interaction.response.defer(thinking=True)
        transfer = await asyncio.to_thread(chain['client'].send, address)
    except ChainError as ex:
        release_request(requester, address, chain)
        logging.error('Token transfer failed for %s to %s in %s: %s',
                      requester, address, chain['chain_id'], ex)
        await send_ephemeral_followup(interaction, GENERIC_ERROR_REPLY)
        return
    except BaseException:
        release_request(requester, address, chain)
        raise

    await interaction.followup.send(await record_transfer(requester, address, chain, transfer))


class FaucetBot(discord.Client):
    """
    Discord client that only uses slash commands (no Message Content Intent)
    """

    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        synced = await self.tree.sync()
        logging.info('Synced slash commands globally: %s',
                     ', '.join(f'/{command.name}' for command in synced))

    async def on_ready(self) -> None:
        """
        Gets called when the Discord client logs in
        """
        logging.info('Logged into Discord as %s', self.user)


def register_commands(tree: app_commands.CommandTree) -> None:
    """
    Register the slash commands. Must be called after load_config,
    since the chain choices come from the config.
    """
    if len(chains) == 1:
        # Single chain: users only need to enter their address
        only_chain = next(iter(chains.values()))

        @tree.command(name='request',
                      description=f'Request {only_chain["chain_id"]} testnet tokens')
        @app_commands.describe(address='Address to send the tokens to')
        @app_commands.guild_only()
        async def request_single(interaction: discord.Interaction,
                                 address: app_commands.Range[str, 1, MAX_ADDRESS_LENGTH]) -> None:
            await handle_request(interaction, only_chain, address)
    else:
        chain_choices = [app_commands.Choice(name=key, value=key) for key in chains]

        @tree.command(name='request', description='Request testnet tokens')
        @app_commands.describe(chain='Chain to receive tokens on',
                               address='Address to send the tokens to')
        @app_commands.choices(chain=chain_choices)
        @app_commands.guild_only()
        async def request_multi(interaction: discord.Interaction,
                                chain: app_commands.Choice[str],
                                address: app_commands.Range[str, 1, MAX_ADDRESS_LENGTH]) -> None:
            await handle_request(interaction, chains[chain.value], address)

    help_message = build_help_message()

    @tree.command(name='help', description='How to use the faucet and which chains it supports')
    @app_commands.guild_only()
    async def help_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            help_message, ephemeral=True, suppress_embeds=True)

    @tree.error
    async def on_command_error(interaction: discord.Interaction,
                               error: app_commands.AppCommandError) -> None:
        logging.error('Command /%s failed: %s',
                      interaction.command.name if interaction.command else '?', error,
                      exc_info=error)
        if interaction.response.is_done():
            await send_ephemeral_followup(interaction, GENERIC_ERROR_REPLY)
        else:
            await interaction.response.send_message(GENERIC_ERROR_REPLY, ephemeral=True)


def main() -> None:
    """
    Main entry point for the Discord bot
    """
    load_config()
    bot = FaucetBot()
    register_commands(bot.tree)
    bot.run(DISCORD_TOKEN)


if __name__ == '__main__':
    main()
