"""
Sets up a Discord bot to provide info and tokens

"""

import asyncio
import time
import datetime
import logging
import sys
import subprocess
from tabulate import tabulate
import aiofiles as aiof
import toml
import discord
import gaia_calls as gaia

from typing import Optional, Tuple

# Turn Down Discord Logging
disc_log = logging.getLogger('discord')
disc_log.setLevel(logging.CRITICAL)

# Configure Logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# Global variables (will be initialized by load_config)
config = None
GAIA_HOME = None
TX_LOG_PATH = None
ADDRESS_PREFIX = None
REQUEST_TIMEOUT = None
DISCORD_TOKEN = None
LISTENING_CHANNELS = None
DENOM = None
chains = None
ACTIVE_REQUESTS = None
chain_locks = {}  # Locks for each chain to prevent race conditions

APPROVE_EMOJI = '✅'
REJECT_EMOJI = '🚫'

# Constants
TX_HASH_LENGTH = 64  # Expected length of transaction hash ID
TWO_HOURS_IN_MINUTES = 120  # Threshold for displaying hours vs minutes


def load_config(config_path: str = 'config.toml') -> None:
    """
    Load configuration from TOML file and initialize global variables
    """
    global config, GAIA_HOME, TX_LOG_PATH, ADDRESS_PREFIX, REQUEST_TIMEOUT
    global DISCORD_TOKEN, LISTENING_CHANNELS, DENOM, chains, ACTIVE_REQUESTS
    
    try:
        config = toml.load(config_path)
    except FileNotFoundError:
        logging.critical('Config file not found: %s', config_path)
        sys.exit(1)
    except toml.TomlDecodeError as ex:
        logging.critical('Failed to parse config file: %s', ex)
        sys.exit(1)

    try:
        GAIA_HOME = config['gaia_home_folder']
        TX_LOG_PATH = config['transactions_log']
        ADDRESS_PREFIX = config['cosmos']['prefix']
        REQUEST_TIMEOUT = int(config['discord']['request_timeout'])
        DISCORD_TOKEN = str(config['discord']['bot_token'])
        LISTENING_CHANNELS = list(
            config['discord']['channels_to_listen'].split(','))
        DENOM = str(config['cosmos']['denomination'])
        chains = config['chains']
        for chain in chains:
            chains[chain]['name'] = chain
            chains[chain]["active_day"] = datetime.datetime.today().date()
            chains[chain]["day_tally"] = 0
            chain_locks[chain] = asyncio.Lock()  # Create lock for each chain
        ACTIVE_REQUESTS = {chain: {} for chain in chains}
    except KeyError as key:
        logging.critical('Key could not be found in config: %s', key)
        sys.exit(1)


HELP_MSG = None  # Will be set after config is loaded


def initialize_help_message() -> None:
    """
    Initialize the help message after config is loaded
    """
    global HELP_MSG
    HELP_MSG = '**List of available commands**\n' \
        '1. Request tokens:\n' \
        '`$request [chain ID] [cosmos address]`\n\n' \
        '2. Query an address balance:\n' \
        '`$balance [chain ID] [cosmos address]`\n\n' \
        '3. Query a transaction:\n' \
        '`$tx_info [chain ID] [transaction hash ID]`\n\n' \
        '4. Query the faucet and node status:\n' \
        '`$faucet_status [chain ID]`\n\n' \
        '5. Query the faucet address: \n' \
        '`$faucet_address [chain ID]`\n\n' \
        f'Example request: `$request {chains[list(chains.keys())[0]]["name"]} cosmos1j7qzunvzx4cdqya80wvnrsmzyt9069d3gwhu5p`\n\n'
    

COMMAND_LIST = [
    '$request',
    '$faucet_status',
    '$faucet_address',
    '$tx_info',
    '$balance'
]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


async def save_transaction_statistics(transaction: str) -> None:
    """
    Transaction strings are already comma-separated
    """
    async with aiof.open(TX_LOG_PATH, 'a') as csv_file:
        await csv_file.write(f'{transaction}\n')
        await csv_file.flush()


async def get_faucet_balance(chain: dict) -> Optional[str]:
    """
    Returns the balance for the chain's denomination, or None if not found
    """
    # Use chain-specific denom if available, otherwise use global DENOM
    target_denom = chain.get('denom', DENOM if DENOM else 'uatom')
    
    balances = gaia.get_balance(
        address=chain['faucet_address'],
        node=chain['node_url'],
        chain_id=chain['chain_id'])
    for balance in balances:
        if balance['denom'] == target_denom:
            return balance['amount'] + target_denom
    return None


async def balance_request(address: str, chain: dict) -> str:
    """
    Provide the balance for a given address and chain
    """
    reply = ''

    try:
        # check address is valid
        result = gaia.check_address(address)
        if result['human'] == ADDRESS_PREFIX:
            try:
                balance = gaia.get_balance(
                    address=address,
                    node=chain["node_url"],
                    chain_id=chain["chain_id"])
                reply = f'Balance for address `{address}` in chain `{chain["chain_id"]}`:\n```\n{tabulate(balance)}\n```\n'
            except (KeyError, ValueError, ConnectionError, TimeoutError, subprocess.CalledProcessError) as ex:
                logging.error('Balance request failed: %s', ex)
                reply = '❗ gaia could not handle your request'
        else:
            reply = f'❗ Expected `{ADDRESS_PREFIX}` prefix'
    except (KeyError, ValueError, TypeError, subprocess.CalledProcessError) as ex:
        logging.error('Address verification failed: %s', ex)
        reply = '❗ gaia could not verify the address'
    return reply


async def faucet_status(chain: dict) -> str:
    """
    Provide node and faucet info
    """
    reply = ''
    logging.info('Faucet status requested for %s', chain['name'])
    try:
        node_status = gaia.get_node_status(node=chain['node_url'])
        if node_status.keys():
            status = f'```\n' \
                f'Node moniker:       {node_status["moniker"]}\n' \
                f'Node last block:    {node_status["last_block"]}\n' \
                f'Faucet address:     {chain["faucet_address"]}\n' \
                f'Amount per request: {chain["amount_to_send"]}{DENOM}\n' \
                f'```'
            reply = status
    except (KeyError, ValueError, ConnectionError, TimeoutError, subprocess.CalledProcessError) as ex:
        logging.error('Faucet status request failed: %s', ex)
        reply = '❗ gaia could not handle your request'
    return reply


async def transaction_info(hash_id: str, chain: dict) -> str:
    """
    Provide info on a specific transaction
    """
    reply = ''
    # Extract hash ID
    if len(hash_id) == TX_HASH_LENGTH:
        try:
            res = gaia.get_tx_info(
                hash_id=hash_id,
                node=chain['node_url'],
                chain_id=chain['chain_id'])
            if res is None:
                return '❗ Transaction is not of type MsgSend or could not be found'
            reply = f'```' \
                f'From:    {res["sender"]}\n' \
                f'To:      {res["receiver"]}\n' \
                f'Amount:  {res["amount"]}\n' \
                f'Height:  {res["height"]}\n```'

        except (KeyError, ValueError, ConnectionError, TimeoutError, subprocess.CalledProcessError) as ex:
            logging.error('Transaction info request failed: %s', ex)
            reply = '❗ gaia could not handle your request'
    else:
        reply = f'❗ Hash ID must be {TX_HASH_LENGTH} characters long, received `{len(hash_id)}`'
    return reply


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


def _check_single_time_limit(entity_id: str, chain: dict, message_timestamp: float) -> Tuple[bool, Optional[str]]:
    """
    Helper function to check if a single entity (user or address) is time-blocked.
    Returns (is_blocked, reply_message)
    """
    chain_requests = ACTIVE_REQUESTS[chain['name']]
    
    if entity_id not in chain_requests:
        return False, None
    
    check_time = chain_requests[entity_id]['next_request']
    if check_time > message_timestamp:
        reply = format_timeout_message(check_time, message_timestamp)
        return True, reply
    
    # Time limit expired, remove the entry
    del chain_requests[entity_id]
    return False, None


def _register_request_limits(requester: str, address: str, chain: dict, message_timestamp: float) -> None:
    """
    Register time limits for both requester and address
    """
    chain_requests = ACTIVE_REQUESTS[chain['name']]
    chain_requests[requester] = {'next_request': message_timestamp + REQUEST_TIMEOUT}
    chain_requests[address] = {'next_request': message_timestamp + REQUEST_TIMEOUT}


def check_time_limits(requester: str, address: str, chain: dict) -> Tuple[bool, Optional[str]]:
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
    Should only be called within a lock
    """
    today = datetime.datetime.today().date()
    if today > chain['active_day']:
        # The date has changed, reset the tally
        chain['active_day'] = today
        chain['day_tally'] = delta
    else:
        chain['day_tally'] += delta


def _build_transaction_request(chain: dict, address: str) -> dict:
    """
    Build the transaction request dictionary
    """
    return {
        'sender': chain['faucet_address'],
        'recipient': address,
        'amount': chain['amount_to_send'] + DENOM,
        'fees': chain['tx_fees'] + DENOM,
        'chain_id': chain['chain_id'],
        'node': chain['node_url']
    }


async def _execute_token_transfer(requester, address: str, chain: dict, delta: int) -> str:
    """
    Execute the token transfer and return the reply message.
    Raises exceptions on failure for rollback handling.
    """
    request = _build_transaction_request(chain, address)
    
    # Make gaia call and send the response back
    transfer = gaia.tx_send(request)
    logging.info('%s requested tokens for %s in %s',
                 requester, address, chain['name'])
    now = datetime.datetime.now()

    # Get faucet balance and save to transaction log
    balance = await get_faucet_balance(chain)
    await save_transaction_statistics(f'{now.isoformat(timespec="seconds")},'
                                      f'{chain["name"]},{address},'
                                      f'{chain["amount_to_send"] + DENOM},'
                                      f'{transfer},'
                                      f'{balance}')
    
    # Format reply with block explorer link or hash
    if chain["block_explorer_tx"]:
        return f'✅  <{chain["block_explorer_tx"]}{transfer}>'
    else:
        return f'✅ Hash ID: {transfer}'

async def token_request(requester, address: str, chain: dict) -> str:
    """
    Send tokens to the specified address
    """
    # Check address
    try:
        # check address is valid
        result = gaia.check_address(address)
        if result['human'] != ADDRESS_PREFIX:
            return f'❗ Expected `{ADDRESS_PREFIX}` prefix'
    except (KeyError, ValueError, TypeError, subprocess.CalledProcessError) as ex:
        logging.error('Address verification failed for %s: %s', address, ex)
        return '❗ The address could not be verified'

    delta = int(chain["amount_to_send"])
    
    # Use lock to prevent race conditions on shared state
    async with chain_locks[chain['name']]:
        # Check whether the faucet has reached the daily cap
        if not check_daily_cap(chain=chain, delta=delta):
            logging.info('%s requested tokens for %s in %s '
                         'but the daily cap has been reached',
                         requester, address, chain['name'])
            return 'Sorry, the daily cap for this faucet has been reached'
        
        # Check whether user or address have received tokens on this chain
        approved, reply = check_time_limits(
            requester=requester.id, address=address, chain=chain)
        
        if not approved:
            logging.info('%s requested tokens for %s in %s and was rejected',
                         requester, address, chain['name'])
            return reply
        
        # Increment the daily tally now that we're committed to the request
        increment_daily_tally(chain, delta)
        
        try:
            reply = await _execute_token_transfer(requester, address, chain, delta)
        except (KeyError, ValueError, ConnectionError, TimeoutError, RuntimeError, subprocess.CalledProcessError) as ex:
            # Rollback state changes on failure
            del ACTIVE_REQUESTS[chain['name']][requester.id]
            del ACTIVE_REQUESTS[chain['name']][address]
            chain['day_tally'] -= delta
            logging.error('Token transfer failed for %s to %s: %s', requester, address, ex)
            reply = '❗ request could not be processed'
    
    return reply


@client.event
async def on_ready() -> None:
    """
    Gets called when the Discord client logs in
    """
    logging.info('Logged into Discord as %s', client.user)


@client.event
async def on_message(message) -> None:
    """
    Responds to messages on specified channels.
    """
    # Ignore messages from the bot itself
    if message.author == client.user:
        return
    
    # Only listen in specific channels (ignore DMs and channels without names)
    if not hasattr(message.channel, 'name') or message.channel.name not in LISTENING_CHANNELS:
        return

    # Validate message content
    if not message.content or not isinstance(message.content, str):
        return

    message_sections = message.content.split(' ')    
    if message.content.startswith('$help'):
        help_reply = HELP_MSG
        help_reply += '**Supported chain IDs**\n'
        for chain, data in chains.items():
            help_reply += f'* `{chain}`\n'
            help_reply += f'  * {data["description"]}\n'
            help_reply += f'  * {data["website"]}\n'
        await message.reply(help_reply)
        return

    if len(message_sections) < 2:
        return

    command = message_sections[0]
    if command in COMMAND_LIST:
        chain_id = message_sections[1]
        if chain_id in chains.keys():
            chain = chains[chain_id]
            if command == '$faucet_address' and len(message_sections) == 2:
                await message.reply(f'The `{chain_id}` faucet has address `{chain["faucet_address"]}`')
            elif command == '$faucet_status' and len(message_sections) == 2:
                await message.reply(await faucet_status(chain))
            elif command == '$tx_info' and len(message_sections) == 3:
                tx_hash = message_sections[2]
                await message.reply(await transaction_info(tx_hash, chain))
            elif command == '$balance' and len(message_sections) == 3:
                address = message_sections[2]
                await message.reply(await balance_request(address, chain))
            elif command == '$request' and len(message_sections) == 3:
                requester = message.author
                address = message_sections[2]
                await message.reply(await token_request(requester, address, chain))
    else:
        logging.info('command not recognized: %s', command)


def main() -> None:
    """
    Main entry point for the Discord bot
    """
    load_config()
    initialize_help_message()
    client.run(DISCORD_TOKEN)


if __name__ == '__main__':
    main()
