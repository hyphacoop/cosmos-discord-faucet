"""
Sets up a Discord bot to provide info and tokens

"""

# import configparser
import time
import datetime
import logging
import sys
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
    VERBOSE_MODE = config['verbose']
    ADDRESS_LENGTH = int(config['cosmos']['address_length'])
    ADDRESS_SUFFIX = config['cosmos']['BECH32_HRP']
    REQUEST_TIMEOUT = int(config['discord']['request_timeout'])
    DISCORD_TOKEN = str(config['discord']['bot_token'])
    LISTENING_CHANNELS = list(
        config['discord']['channels_to_listen'].split(','))
    GAS_PRICE = float(config['request']['gas_price'])
    GAS_LIMIT = float(config['request']['gas_limit'])
    AMOUNT_TO_SEND = str(config['request']['amount_to_send']) + \
        str(config['cosmos']['denomination'])
    testnets = config['testnets']
    for net in testnets:
        testnets[net]["name"] = net
    TESTNET_OPTIONS = '|'.join(list(testnets.keys()))
except KeyError as key:
    logging.critical('Key could not be found: %s', key)
    sys.exit()

APPROVE_EMOJI = '✅'
REJECT_EMOJI = '🚫'

help_msg = '**List of available commands:**\n' \
    '1. Request tokens through the faucet:\n' \
    f'`$request [cosmos address] {TESTNET_OPTIONS}`\n\n' \
    '2. Request the faucet and node status:\n' \
    f'`$faucet_status {TESTNET_OPTIONS}`\n\n' \
    '3. Request the faucet address: \n' \
    f'`$faucet_address {TESTNET_OPTIONS}`\n\n' \
    '4. Request information for a specific transaction:\n'\
    f'`$tx_info [transaction hash ID] {TESTNET_OPTIONS}`\n\n' \
    '5. Request the address balance:\n' \
    f'`$balance [cosmos address] {TESTNET_OPTIONS}`'

ACTIVE_REQUESTS = {'vega': dict(), 'theta': dict()}
client = discord.Client()


async def save_transaction_statistics(transaction: str):
    """
    Transaction strings are already comma-separated
    """
    async with aiof.open('transactions.csv', 'a') as csv_file:
        await csv_file.write(f'{transaction}\n')
        await csv_file.flush()


async def balance_request(message, testnet: dict):
    """
    Provide the balance for a given address and testnet
    """
    reply = ''
    address = str(message.content).split(' ')
    if len(address) != 3:
        await message.reply(help_msg)
    address.remove(testnet['name'])
    address.remove('$balance')
    address = address[0]

    if len(address) == ADDRESS_LENGTH:
        try:
            balance = gaia.get_balance(
                address=address,
                node=testnet["node_url"],
                chain_id=testnet["chain_id"])
            reply = f'Address  `{address}`  has a balance of' \
                    f'  `{balance["amount"]}{balance["denom"]}`  '  \
                    f'in testnet  `{testnet["name"]}`'
        except Exception as exc:
            reply = '❗ gaia could not handle your request'
    else:
        reply = f'Address must be {ADDRESS_LENGTH} characters long,' \
                f'received `{len(address)}`'
    await message.reply(reply)


async def faucet_status(message, testnet: dict):
    """
    Provide node and faucet info
    """
    reply = ''
    try:
        node_status = gaia.get_node_status(node=testnet['node_url'])
        amount, denom = gaia.get_balance(
            address=testnet['faucet_address'],
            node=testnet['node_url'],
            chain_id=testnet['chain_id'])
        if node_status.keys() and amount:
            status = f'```\n' \
                f'Node moniker:      {node_status["moniker"]}\n' \
                f'Node last block:   {node_status["last_block"]}\n' \
                f'Faucet address:    {testnet["faucet_address"]}\n' \
                f'Faucet balance:    {amount}{denom}' \
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
    hash_id = str(message.content).split(' ')
    if len(hash_id) != 3:
        return help_msg
    hash_id.remove(testnet['name'])
    hash_id.remove('$tx_info')
    hash_id = hash_id[0]
    if len(hash_id) == 64:
        try:
            res = gaia.get_tx_info(
                hash_id=hash_id,
                node=testnet['node_url'],
                chain_id=testnet['chain_id'])
            reply = f'```' \
                f'From:    {res["sender"]}\n' \
                f'To:      {res["recipient"]}\n' \
                f'Amount:  {res["amount"]}\n```'

        except Exception:
            reply = '❗ gaia could not handle your request'
    else:
        reply = f'Hash ID must be 64 characters long, received `{len(hash_id)}`'
    await message.reply(reply)


async def token_request(message, testnet: dict):
    """
    Send tokens to the specified address
    """
    address = str(message.content).lower().split(" ")
    if len(address) != 3:
        await message.reply(help_msg)
    address.remove(testnet['name'])
    address.remove('$request')
    address = address[0]
    message_timestamp = time.time()
    requester = message.author
    if len(address) != ADDRESS_LENGTH or address[:len(ADDRESS_SUFFIX)] != ADDRESS_SUFFIX:
        await message.reply(f'Invalid address format: `{address}`:\n'
                            f'Address length must be `{ADDRESS_LENGTH}`'
                            f' and the suffix must be `{ADDRESS_SUFFIX}`')

    # Check user allowance
    if requester.id in ACTIVE_REQUESTS[testnet['name']]:
        check_time = ACTIVE_REQUESTS[testnet['name']
                                     ][requester.id]['next_request']
        if check_time > message_timestamp:
            timeout_in_hours = int(REQUEST_TIMEOUT) / 60 / 60
            await message.reply(f'{REJECT_EMOJI} You can request coins no more than once every'
                                f' {timeout_in_hours:.0f} hours, '
                                f'please try again in '
                                f'{round((check_time - message_timestamp) / 60, 2):.0f} minutes')
            return
        else:
            del ACTIVE_REQUESTS[testnet['name']][requester.id]

    # Check address allowance
    if address in ACTIVE_REQUESTS[testnet['name']]:
        check_time = ACTIVE_REQUESTS[testnet['name']][address]["next_request"]
        if check_time > message_timestamp:
            timeout_in_hours = int(REQUEST_TIMEOUT) / 60 / 60
            await message.reply(f'{REJECT_EMOJI} You can request coins no more than once every'
                                f' {timeout_in_hours:.0f} hours, '
                                f'please try again in '
                                f'{round((check_time - message_timestamp) / 60, 2):.0f} minutes')
            return
        else:
            del ACTIVE_REQUESTS[testnet['name']][address]

    if requester.id not in ACTIVE_REQUESTS[testnet['name']] and \
       address not in ACTIVE_REQUESTS[testnet['name']]:
        ACTIVE_REQUESTS[testnet['name']][requester.id] = {
            'requester': requester,
            'next_request': message_timestamp + REQUEST_TIMEOUT}
        ACTIVE_REQUESTS[testnet['name']][address] = {
            'next_request': message_timestamp + REQUEST_TIMEOUT}

    try:
        transfer = gaia.tx_send(
            sender=testnet['faucet_address'],
            recipient=address,
            amount=AMOUNT_TO_SEND,
            chain_id=testnet["chain_id"],
            node=testnet["node_url"])
    except Exception:
        await message.reply('❗ request could not be processed')
        del ACTIVE_REQUESTS[testnet['name']][requester.id]
        del ACTIVE_REQUESTS[testnet['name']][address]
    logging.info('%s requested tokens for %s in %s',
                 requester, address, testnet['name'])
    now = datetime.datetime.now()
    await save_transaction_statistics(f'{now.strftime("%Y-%m-%d,%H:%M:%S")},'
                                      f'{testnet["name"]},{address},{AMOUNT_TO_SEND},{transfer}')
    await message.reply(f'✅  <{testnet["block_explorer_tx"]}{transfer}>')


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
        await message.reply(help_msg)
        return

    # User needs to specify testnet
    for name in list(testnets.keys()):
        if name in message.content:
            testnet = testnets[name]
            # Dispatch message to appropriate handler
            if message.content.startswith('$faucet_address'):
                await message.reply(f'The {testnet["name"]} \testnet has address '
                                    f'`{testnet["faucet_address"]}`')
            elif message.content.startswith('$balance'):
                await balance_request(message, testnet)
            elif message.content.startswith('$faucet_status'):
                await faucet_status(message, testnet)
            elif message.content.startswith('$tx_info'):
                await transaction_info(message, testnet)
            elif message.content.startswith('$request'):
                await token_request(message, testnet)
            break


client.run(DISCORD_TOKEN)
