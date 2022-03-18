"""
Sets up a Discord bot to provide info and tokens

"""

import configparser
import time
import datetime
import logging
import sys
import aiofiles as aiof
import discord
import gaia_calls as gaia

# Turn Down Discord Logging
disc_log = logging.getLogger('discord')
disc_log.setLevel(logging.CRITICAL)

# Configure Logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# Load config
c = configparser.ConfigParser()
c.read("config.ini", encoding='utf-8')

try:
    VERBOSE_MODE = str(c["DEFAULT"]["verbose"])
    ADDRESS_LENGTH = int(c["DEFAULT"]["address_length"])
    ADDRESS_SUFFIX = str(c["DEFAULT"]["BECH32_HRP"])
    REQUEST_TIMEOUT = int(c["DISCORD"]["request_timeout"])
    DISCORD_TOKEN = str(c["DISCORD"]["bot_token"])
    LISTENING_CHANNELS = list(c["DISCORD"]["channels_to_listen"].split(","))
except KeyError as key:
    logging.critical("Configuration could not be read for %s", key)
    sys.exit()

APPROVE_EMOJI = "✅"
REJECT_EMOJI = "🚫"
ACTIVE_REQUESTS = {"vega": dict(), "theta": dict()}
client = discord.Client()

try:
    with open("help_msg.txt", "r", encoding="utf-8") as help_file:
        help_msg = help_file.read()
except FileNotFoundError as fnf:
    logging.critical("%s", fnf)
    sys.exit()


async def save_transaction_statistics(transaction: str):
    """
    Transaction strings are already comma-separated
    """
    async with aiof.open("transactions.csv", "a") as csv_file:
        await csv_file.write(f'{transaction}\n')
        await csv_file.flush()


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

    # User needs to specify testnet: they only have to say "vega" or "theta"
    testnet = ''
    testnet_name = ''
    if "vega" in message.content:
        testnet = gaia.testnets["vega"]
        testnet_name = "vega"
    elif "theta" in message.content:
        testnet = gaia.testnets["theta"]
        testnet_name = "theta"
    else:
        await message.reply(f"Please specify which testnet you would like tokens for:"
                            " **vega** or **theta**\n"
                            f"{help_msg}")
        return

    # Respond to $help
    if message.content.startswith('$help'):
        await message.reply(help_msg)

    # Provide the faucet address
    if message.content.startswith('$faucet_address') or message.content.startswith('$tap_address'):
        await message.reply(f'The {testnet_name} testnet has address `{testnet["faucet"]}`')

    # Provide the balance for a given address
    if message.content.startswith('$balance'):
        address = str(message.content).split(' ')
        if len(address) != 3:
            await message.reply(help_msg)
            return
        address.remove(testnet_name)
        address.remove('$balance')
        address = address[0]
        requester = message.author
        # Log request
        logging.info("Balance request: %s : %s", requester.name, address)

        if len(address) == ADDRESS_LENGTH:
            try:
                balance = gaia.get_balance(
                    testnet_name=testnet_name, address=address)
                if balance.keys():
                    await message.reply(f'Address  `{address}`  has a balance of'
                                        f'  `{balance["amount"]}{balance["denom"]}`  '
                                        f'in testnet  `{testnet_name}`')
                else:
                    await message.reply('Account is not initialized (balance is empty)')
            except Exception as e:
                print(type(e))
                await message.reply("❗ gaia could not handle your request")
        else:
            await message.reply(f'Address must be {gaia.ADDRESS_LENGTH} characters long,'
                                f'received `{len(address)}`')

    # Show node and faucet info
    if message.content.startswith('$faucet_status'):
        # Log request
        requester = message.author
        logging.info("Status request: %s", requester.name)

        try:
            node_status = gaia.get_node_status(testnet_name=testnet_name)
            faucet_balance = gaia.get_balance(
                testnet_name=testnet_name, address=testnet["faucet"])
            if node_status.keys() and faucet_balance.keys():
                status = f'```\n' \
                    f'Node moniker:      {node_status["moniker"]}\n' \
                    f'Node catching up?  {node_status["syncs"]}\n' \
                    f'Node last block:   {node_status["last_block"]}\n' \
                    f'Faucet address:    {testnet["faucet"]}\n' \
                    f'Faucet balance:    {faucet_balance["amount"]}{faucet_balance["denom"]}' \
                    f'```'
                await message.reply(status)

        except Exception:
            await message.reply("❗ gaia could not handle your request")

    # Provide info on a specific transaction
    if message.content.startswith('$tx_info'):
        hash_id = str(message.content).split(' ')
        if len(hash_id) != 3:
            await message.reply(help_msg)
            return
        hash_id.remove(testnet_name)
        hash_id.remove('$tx_info')
        hash_id = hash_id[0]
        if len(hash_id) == 64:
            try:
                res = gaia.get_tx_info(
                    testnet_name=testnet_name, transaction=hash_id)
                tx_info = f'```' \
                    f'From:    {res["sender"]}\n' \
                    f'To:      {res["recipient"]}\n' \
                    f'Amount:  {res["amount"]}\n```'
                await message.reply(tx_info)
            except Exception:
                await message.reply("❗ gaia could not handle your request")
        else:
            await message.reply(f'Hash ID must be 64 characters long, received `{len(hash_id)}`')

    # Send tokens to the specified address
    if message.content.startswith('$request'):
        address = str(message.content).lower().split(" ")
        if len(address) != 3:
            await message.reply(help_msg)
            return
        address.remove(testnet_name)
        address.remove('$request')
        address = address[0]
        message_timestamp = time.time()
        requester = message.author
        if len(address) != ADDRESS_LENGTH or address[:len(ADDRESS_SUFFIX)] != ADDRESS_SUFFIX:
            await message.reply(f'Invalid address format: `{address}`:\n'
                                f'Address length must be `{ADDRESS_LENGTH}`'
                                f' and the suffix must be `{ADDRESS_SUFFIX}`')
            return

        # Check user allowance
        if requester.id in ACTIVE_REQUESTS[testnet_name]:
            check_time = ACTIVE_REQUESTS[testnet_name][requester.id]["next_request"]
            if check_time > message_timestamp:
                timeout_in_hours = int(REQUEST_TIMEOUT) / 60 / 60
                please_wait_text = f'You can request coins no more than once every'\
                                   f' {timeout_in_hours:.0f} hours, ' \
                                   f'please try again in ' \
                                   f'{round((check_time - message_timestamp) / 60, 2):.0f} minutes'
                await message.reply(please_wait_text)

            else:
                del ACTIVE_REQUESTS[testnet_name][requester.id]

        # Check address allowance
        if address in ACTIVE_REQUESTS[testnet_name]:
            check_time = ACTIVE_REQUESTS[testnet_name][address]["next_request"]
            if check_time > message_timestamp:
                timeout_in_hours = int(REQUEST_TIMEOUT) / 60 / 60
                please_wait_text = f'You can request coins no more than once every'\
                                   f' {timeout_in_hours:.0f} hours, ' \
                                   f'please try again in ' \
                                   f'{round((check_time - message_timestamp) / 60, 2):.0f} minutes'
                await message.reply(please_wait_text)

            else:
                del ACTIVE_REQUESTS[testnet_name][address]

        if requester.id not in ACTIVE_REQUESTS[testnet_name] and \
           address not in ACTIVE_REQUESTS[testnet_name]:
            ACTIVE_REQUESTS[testnet_name][requester.id] = {
                "requester": requester,
                "next_request": message_timestamp + REQUEST_TIMEOUT}
            ACTIVE_REQUESTS[testnet_name][address] = {
                "next_request": message_timestamp + REQUEST_TIMEOUT}

            try:
                transfer = gaia.tx_send(
                    testnet_name=testnet_name, recipient=address)

            except Exception:
                await message.reply("❗ request could not be processed")
                del ACTIVE_REQUESTS[testnet_name][requester.id]
                del ACTIVE_REQUESTS[testnet_name][address]

            logging.info("%s requested tokens for %s", requester, address)
            now = datetime.datetime.now()
            await save_transaction_statistics(f'{now.strftime("%Y-%m-%d,%H:%M:%S")},'
                                              f'{testnet_name},{address},{transfer[2]["value"]}')
            await message.reply("✅")


client.run(DISCORD_TOKEN)
