"""
Sets up a Discord bot to provide info and tokens

"""

# import configparser
import time
import datetime
import logging
import sys
from tabulate import tabulate
import aiofiles as aiof
import toml
import discord
import gaia_calls as gaia

# Turn Down Discord Logging
disc_log = logging.getLogger('discord')
disc_log.setLevel(logging.CRITICAL)

# Configure Logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# Load config
config = toml.load('config.toml')

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
    ACTIVE_REQUESTS = {chain: {} for chain in chains}
except KeyError as key:
    logging.critical('Key could not be found: %s', key)
    sys.exit()

APPROVE_EMOJI = '✅'
REJECT_EMOJI = '🚫'

HELP_MSG = '**List of available commands**\n' \
    '1. Request tokens:\n' \
    '`$request [chain ID] [cosmos address]`\n\n' \
    '2. Query an address balance:\n' \
    '`$balance [chain ID] [cosmos address]`\n\n' \
    '3. Query a transaction:\n'\
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

client = discord.Client()


async def save_transaction_statistics(transaction: str):
    """
    Transaction strings are already comma-separated
    """
    async with aiof.open(TX_LOG_PATH, 'a') as csv_file:
        await csv_file.write(f'{transaction}\n')
        await csv_file.flush()


async def get_faucet_balance(chain: dict):
    """
    Returns the uatom balance
    """
    balances = gaia.get_balance(
        address=chain['faucet_address'],
        node=chain['node_url'],
        chain_id=chain['chain_id'])
    for balance in balances:
        if balance['denom'] == 'uatom':
            return balance['amount']+'uatom'


async def balance_request(address, chain: dict):
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
                reply = f'Balance for address `{address}` in chain `{chain["chain_id"]}`:\n```'
                reply = reply + tabulate(balance)
                reply = reply + '\n```\n'
            except Exception:
                reply = '❗ gaia could not handle your request'
        else:
            reply = f'❗ Expected `{ADDRESS_PREFIX}` prefix'
    except Exception:
        reply = '❗ gaia could not verify the address'
    return reply


async def faucet_status(chain: dict):
    """
    Provide node and faucet info
    """
    reply = ''
    try:
        node_status = gaia.get_node_status(node=chain['node_url'])
        balance = gaia.get_balance(
            address=chain['faucet_address'],
            node=chain['node_url'],
            chain_id=chain['chain_id'])
        if node_status.keys() and balance:
            status = f'```\n' \
                f'Node moniker:       {node_status["moniker"]}\n' \
                f'Node last block:    {node_status["last_block"]}\n' \
                f'Faucet address:     {chain["faucet_address"]}\n' \
                f'Amount per request: {chain["amount_to_send"]}{DENOM}\n' \
                f'```'
            reply = status
    except Exception:
        reply = '❗ gaia could not handle your request'
    return reply


async def transaction_info(hash_id, chain: dict):
    """
    Provide info on a specific transaction
    """
    reply = ''
    # Extract hash ID
    if len(hash_id) == 64:
        try:
            res = gaia.get_tx_info(
                hash_id=hash_id,
                node=chain['node_url'],
                chain_id=chain['chain_id'])
            reply = f'```' \
                f'From:    {res["sender"]}\n' \
                f'To:      {res["receiver"]}\n' \
                f'Amount:  {res["amount"]}\n' \
                f'Height:  {res["height"]}\n```'

        except Exception:
            reply = '❗ gaia could not handle your request'
    else:
        reply = f'❗ Hash ID must be 64 characters long, received `{len(hash_id)}`'
    return reply


def check_time_limits(requester: str, address: str, chain: dict):
    """
    Returns True, None if the given requester and address are not time-blocked for the given chain
    Returns False, reply if either of them is still on time-out; msg is the reply to the requester
    """
    message_timestamp = time.time()
    # Check user allowance
    if requester in ACTIVE_REQUESTS[chain['name']]:
        check_time = ACTIVE_REQUESTS[chain['name']
                                     ][requester]['next_request']
        if check_time > message_timestamp:
            seconds_left = check_time - message_timestamp
            minutes_left = seconds_left / 60
            if minutes_left > 120:
                wait_time = str(int(minutes_left/60)) + ' hours'
            else:
                wait_time = str(int(minutes_left)) + ' minutes'
            timeout_in_hours = int(REQUEST_TIMEOUT / 60 / 60)
            timeout_in_hours = int(REQUEST_TIMEOUT / 60 / 60)
            reply = f'{REJECT_EMOJI} You can request coins no more than once every' \
                f' {timeout_in_hours} hours for the same chain, ' \
                f'please try again in ' \
                f'{wait_time}'
            return False, reply
        del ACTIVE_REQUESTS[chain['name']][requester]

    # Check address allowance
    if address in ACTIVE_REQUESTS[chain['name']]:
        check_time = ACTIVE_REQUESTS[chain['name']][address]['next_request']
        if check_time > message_timestamp:
            seconds_left = check_time - message_timestamp
            minutes_left = seconds_left / 60
            if minutes_left > 120:
                wait_time = str(int(minutes_left/60)) + ' hours'
            else:
                wait_time = str(int(minutes_left)) + ' minutes'
            timeout_in_hours = int(REQUEST_TIMEOUT / 60 / 60)
            reply = f'{REJECT_EMOJI} You can request coins no more than once every' \
                f' {timeout_in_hours} hours, for the same chain, ' \
                f'please try again in ' \
                f'{wait_time}'
            return False, reply
        del ACTIVE_REQUESTS[chain['name']][address]

    if requester not in ACTIVE_REQUESTS[chain['name']] and \
       address not in ACTIVE_REQUESTS[chain['name']]:
        ACTIVE_REQUESTS[chain['name']][requester] = {
            'next_request': message_timestamp + REQUEST_TIMEOUT}
        ACTIVE_REQUESTS[chain['name']][address] = {
            'next_request': message_timestamp + REQUEST_TIMEOUT}

    return True, None


def check_daily_cap(chain: dict):
    """
    Returns True if the faucet has not reached the daily cap
    Returns False otherwise
    """
    delta = int(chain["amount_to_send"])
    # Check date
    today = datetime.datetime.today().date()
    if today != chain['active_day']:
        # The date has changed, reset the tally
        chain['active_day'] = today
        chain['day_tally'] = delta
        return True

    # Check tally
    if chain['day_tally'] + delta > int(chain['daily_cap']):
        return False

    chain['day_tally'] += delta
    return True


async def token_request(requester, address, chain: dict):
    """
    Send tokens to the specified address
    """
    # Check address
    try:
        # check address is valid
        result = gaia.check_address(address)
        if result['human'] != ADDRESS_PREFIX:
            await message.reply(f'❗ Expected `{ADDRESS_PREFIX}` prefix')
            return
    except Exception:
        await message.reply('❗ gaia could not verify the address')
        return

    # Check whether the faucet has reached the daily cap
    if check_daily_cap(chain=chain):
        # Check whether user or address have received tokens on this chain
        approved, reply = check_time_limits(
            requester=requester.id, address=address, chain=chain)
        if approved:
            request = {'sender': chain['faucet_address'],
                       'recipient': address,
                       'amount': chain['amount_to_send'] + DENOM,
                       'fees': chain['tx_fees'] + DENOM,
                       'chain_id': chain['chain_id'],
                       'node': chain['node_url']}
            try:
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
                if chain["block_explorer_tx"]:
                    reply = f'✅  <{chain["block_explorer_tx"]}{transfer}>'
                else:
                    reply = f'✅ Hash ID: {transfer}'
            except Exception as ex:
                del ACTIVE_REQUESTS[chain['name']][requester.id]
                del ACTIVE_REQUESTS[chain['name']][address]
                chain['day_tally'] -= int(chain['amount_to_send'])
                logging.info(ex)
                reply = '❗ request could not be processed'
        else:
            chain['day_tally'] -= int(chain['amount_to_send'])
            logging.info('%s requested tokens for %s in %s and was rejected',
                         requester, address, chain['name'])
    else:
        logging.info('%s requested tokens for %s in %s '
                     'but the daily cap has been reached',
                     requester, address, chain['name'])
        reply = 'Sorry, the daily cap for this faucet has been reached'
    return reply


@client.event
async def on_ready():
    """
    Gets called when the Discord client logs in
    """
    logging.info('Logged into Discord as %s', client.user)


@client.event
async def on_message(message):
    """
    Responds to messages on specified channels.
    """
    # Only listen in specific channels, and do not listen to your own messages
    if (message.channel.name not in LISTENING_CHANNELS) or (message.author == client.user):
        return

    message_sections = message.content.split(' ')    
    if message.content.startswith('$help'):
        help_reply = HELP_MSG
        help_reply += '**Supported chain IDs**\n'
        for chain, data in chains.items():
            help_reply += f'* `{chain}`\n'
            help_reply += f' * {data["description"]}\n'
            help_reply += f' * <{data["website"]}>\n'
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
                hash = message_sections[2]
                await message.reply(await transaction_info(hash, chain))
            elif message.content.startswith('$balance') and len(message_sections) == 3:
                address = message_sections[2]
                await message.reply(await balance_request(address, chain))
            elif message.content.startswith('$request') and len(message_sections) == 3:
                requester = message.author
                address = message_sections[2]
                await message.reply(await token_request(requester, address, chain))
    else:
        logging.info(f'command not recognized: {command}')

client.run(DISCORD_TOKEN)
