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
    ADDRESS_PREFIX = config['cosmos']['prefix']
    REQUEST_TIMEOUT = int(config['discord']['request_timeout'])
    DISCORD_TOKEN = str(config['discord']['bot_token'])
    LISTENING_CHANNELS = list(
        config['discord']['channels_to_listen'].split(','))
    DENOM = str(config['cosmos']['denomination'])
    testnets = config['testnets']
    for net in testnets:
        testnets[net]['name'] = net
        testnets[net]["active_day"] = datetime.datetime.today().date()
        testnets[net]["day_tally"] = 0
    ACTIVE_REQUESTS = {net: {} for net in testnets}
except KeyError as key:
    logging.critical('Key could not be found: %s', key)
    sys.exit()

APPROVE_EMOJI = '✅'
REJECT_EMOJI = '🚫'

HELP_MSG = '**List of available commands:**\n' \
    '1. Request tokens through the faucet:\n' \
    '`$request [cosmos address]`\n\n' \
    '2. Request the faucet and node status:\n' \
    '`$faucet_status`\n\n' \
    '3. Request the faucet address: \n' \
    '`$faucet_address`\n\n' \
    '4. Request information for a specific transaction:\n'\
    '`$tx_info [transaction hash ID]`\n\n' \
    '5. Request the address balance:\n' \
    '`$balance [cosmos address]`'


client = discord.Client()


async def save_transaction_statistics(transaction: str):
    """
    Transaction strings are already comma-separated
    """
    async with aiof.open('transactions.csv', 'a') as csv_file:
        await csv_file.write(f'{transaction}\n')
        await csv_file.flush()


async def get_faucet_balance(testnet: dict):
    """
    Returns the uatom balance
    """
    balances = gaia.get_balance(
        address=testnet['faucet_address'],
        node=testnet['node_url'],
        chain_id=testnet['chain_id'])
    for balance in balances:
        if balance['denom'] == 'uatom':
            return balance['amount']+'uatom'


async def balance_request(message, testnet: dict):
    """
    Provide the balance for a given address and testnet
    """
    reply = ''
    # Extract address
    message_sections = str(message.content).split()
    if len(message_sections) != 2:
        await message.reply(HELP_MSG)
    address = message_sections[1]

    try:
        # check address is valid
        result = gaia.check_address(address)
        if result['human'] == ADDRESS_PREFIX:
            try:
                balance = gaia.get_balance(
                    address=address,
                    node=testnet["node_url"],
                    chain_id=testnet["chain_id"])
                reply = f'Balance for address `{address}` in chain `{testnet["chain_id"]}`:\n```'
                reply = reply + tabulate(balance)
                reply = reply + '\n```\n'
            except Exception:
                reply = '❗ gaia could not handle your request'
        else:
            reply = f'❗ Expected `{ADDRESS_PREFIX}` prefix'
    except Exception:
        reply = '❗ gaia could not verify the address'
    await message.reply(reply)


async def faucet_status(message, testnet: dict):
    """
    Provide node and faucet info
    """
    reply = ''
    try:
        node_status = gaia.get_node_status(node=testnet['node_url'])
        balance = gaia.get_balance(
            address=testnet['faucet_address'],
            node=testnet['node_url'],
            chain_id=testnet['chain_id'])
        if node_status.keys() and balance:
            status = f'```\n' \
                f'Node moniker:      {node_status["moniker"]}\n' \
                f'Node last block:   {node_status["last_block"]}\n' \
                f'Faucet address:    {testnet["faucet_address"]}\n' \
                f'```'
            reply = status
    except Exception:
        reply = '❗ gaia could not handle your request'
    await message.reply(reply)


async def transaction_info(message, testnet: dict):
    """
    Provide info on a specific transaction
    """
    reply = ''
    # Extract hash ID
    message_sections = str(message.content).split()
    if len(message_sections) != 2:
        return HELP_MSG
    hash_id = message_sections[1]
    if len(hash_id) == 64:
        try:
            res = gaia.get_tx_info(
                hash_id=hash_id,
                node=testnet['node_url'],
                chain_id=testnet['chain_id'])
            reply = f'```' \
                f'From:    {res["sender"]}\n' \
                f'To:      {res["receiver"]}\n' \
                f'Amount:  {res["amount"]}\n' \
                f'Height:  {res["height"]}\n```'

        except Exception:
            reply = '❗ gaia could not handle your request'
    else:
        reply = f'❗ Hash ID must be 64 characters long, received `{len(hash_id)}`'
    await message.reply(reply)


def check_time_limits(requester: str, address: str, testnet: dict):
    """
    Returns True, None if the given requester and address are not time-blocked for the given testnet
    Returns False, reply if either of them is still on time-out; msg is the reply to the requester
    """
    message_timestamp = time.time()
    # Check user allowance
    if requester in ACTIVE_REQUESTS[testnet['name']]:
        check_time = ACTIVE_REQUESTS[testnet['name']
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
                f' {timeout_in_hours} hours for the same testnet, ' \
                f'please try again in ' \
                f'{wait_time}'
            return False, reply
        del ACTIVE_REQUESTS[testnet['name']][requester]

    # Check address allowance
    if address in ACTIVE_REQUESTS[testnet['name']]:
        check_time = ACTIVE_REQUESTS[testnet['name']][address]['next_request']
        if check_time > message_timestamp:
            seconds_left = check_time - message_timestamp
            minutes_left = seconds_left / 60
            if minutes_left > 120:
                wait_time = str(int(minutes_left/60)) + ' hours'
            else:
                wait_time = str(int(minutes_left)) + ' minutes'
            timeout_in_hours = int(REQUEST_TIMEOUT / 60 / 60)
            reply = f'{REJECT_EMOJI} You can request coins no more than once every' \
                f' {timeout_in_hours} hours, for the same testnet, ' \
                f'please try again in ' \
                f'{wait_time}'
            return False, reply
        del ACTIVE_REQUESTS[testnet['name']][address]

    if requester not in ACTIVE_REQUESTS[testnet['name']] and \
       address not in ACTIVE_REQUESTS[testnet['name']]:
        ACTIVE_REQUESTS[testnet['name']][requester] = {
            'next_request': message_timestamp + REQUEST_TIMEOUT}
        ACTIVE_REQUESTS[testnet['name']][address] = {
            'next_request': message_timestamp + REQUEST_TIMEOUT}

    return True, None


def check_daily_cap(testnet: dict):
    """
    Returns True if the faucet has not reached the daily cap
    Returns False otherwise
    """
    delta = int(testnet["amount_to_send"])
    # Check date
    today = datetime.datetime.today().date()
    if today != testnet['active_day']:
        # The date has changed, reset the tally
        testnet['active_day'] = today
        testnet['day_tally'] = delta
        return True

    # Check tally
    if testnet['day_tally'] + delta > int(testnet['daily_cap']):
        return False

    testnet['day_tally'] += delta
    return True


async def token_request(message, testnet: dict):
    """
    Send tokens to the specified address
    """
    # Extract address
    message_sections = str(message.content).lower().split()
    if len(message_sections) < 2:
        await message.reply(HELP_MSG)
    address = message_sections[1]

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

    requester = message.author
    # Check whether the faucet has reached the daily cap
    if check_daily_cap(testnet=testnet):
        # Check whether user or address have received tokens on this testnet
        approved, reply = check_time_limits(
            requester=requester.id, address=address, testnet=testnet)
        if approved:
            request = {'sender': testnet['faucet_address'],
                       'recipient': address,
                       'amount': testnet['amount_to_send'] + DENOM,
                       'fees': testnet['tx_fees'] + DENOM,
                       'chain_id': testnet['chain_id'],
                       'node': testnet['node_url']}
            try:
                # Make gaia call and send the response back
                transfer = gaia.tx_send(request)
                logging.info('%s requested tokens for %s in %s',
                             requester, address, testnet['name'])
                now = datetime.datetime.now()
                if testnet["block_explorer_tx"]:
                    await message.reply(f'✅  <{testnet["block_explorer_tx"]}{transfer}>')
                else:
                    await message.reply(f'✅ Hash ID: {transfer}')
                # Get faucet balance and save to transaction log
                balance = await get_faucet_balance(testnet)
                await save_transaction_statistics(f'{now.isoformat(timespec="seconds")},'
                                                  f'{testnet["name"]},{address},'
                                                  f'{testnet["amount_to_send"] + DENOM},'
                                                  f'{transfer},'
                                                  f'{balance}')
            except Exception:
                await message.reply('❗ request could not be processed')
                del ACTIVE_REQUESTS[testnet['name']][requester.id]
                del ACTIVE_REQUESTS[testnet['name']][address]
                testnet['day_tally'] -= int(testnet['amount_to_send'])
        else:
            testnet['day_tally'] -= int(testnet['amount_to_send'])
            logging.info('%s requested tokens for %s in %s and was rejected',
                         requester, address, testnet['name'])
            await message.reply(reply)
    else:
        logging.info('%s requested tokens for %s in %s '
                     'but the daily cap has been reached',
                     requester, address, testnet['name'])
        await message.reply("Sorry, the daily cap for this faucet has been reached")


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

    # Respond to $help
    if message.content.startswith('$help'):
        await message.reply(HELP_MSG)
        return

    testnet = testnets['theta']
    # Dispatch message to appropriate handler
    if message.content.startswith('$faucet_address'):
        await message.reply(f'The {testnet["name"]} faucet has address'
                            f'  `{testnet["faucet_address"]}`')
    elif message.content.startswith('$balance'):
        await balance_request(message, testnet)
    elif message.content.startswith('$faucet_status'):
        await faucet_status(message, testnet)
    elif message.content.startswith('$tx_info'):
        await transaction_info(message, testnet)
    elif message.content.startswith('$request'):
        await token_request(message, testnet)

client.run(DISCORD_TOKEN)
