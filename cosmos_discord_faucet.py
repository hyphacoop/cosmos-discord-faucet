import aiofiles as aiof
import discord
import configparser
import time
import logging
import datetime
import sys
import subprocess
import json
import gaia_calls as gaia

# Turn Down Discord Logging
disc_log = logging.getLogger('discord')
disc_log.setLevel(logging.CRITICAL)

# Configure Logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

# Load config
c = configparser.ConfigParser()
c.read("config.ini", encoding='utf-8')

VERBOSE_MODE = str(c["DEFAULT"]["verbose"])
ADDRESS_LENGTH = int(c["DEFAULT"]["address_length"])
ADDRESS_SUFFIX = str(c["DEFAULT"]["BECH32_HRP"])
REQUEST_TIMEOUT = int(c["DISCORD"]["request_timeout"])
DISCORD_TOKEN = str(c["DISCORD"]["bot_token"])
LISTENING_CHANNELS = list(c["DISCORD"]["channels_to_listen"].split(","))

APPROVE_EMOJI = "✅"
REJECT_EMOJI = "🚫"
ACTIVE_REQUESTS = {"vega": dict(),"theta": dict()}
client = discord.Client()

with open("help_msg.txt", "r", encoding="utf-8") as help_file:
    help_msg = help_file.read()

async def save_transaction_statistics(some_string: str):
    async with aiof.open("transactions.csv", "a") as csv_file:
        await csv_file.write(f'{some_string}\n')
        await csv_file.flush()

@client.event
async def on_ready():
    logger.info(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    message_timestamp = time.time()
    requester = message.author

    # Only listen in specific channels, and do not listen to your own messages
    if (message.channel.name not in LISTENING_CHANNELS) or (message.author == client.user):
        return

    # Respond to $help
    if message.content.startswith('$help'):
        await message.reply(help_msg)
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
        await message.reply(f"Please specify which testnet you would like tokens for: **vega** or **theta**\n" \
            f"{help_msg}")
        return

    # Provide the faucet address
    if message.content.startswith('$faucet_address') or message.content.startswith('$tap_address'):
        try:
            await message.reply(f'The {testnet_name} testnet has address `{testnet["faucet"]}`')
        except:
            print("Can't send message $faucet_address")
        return

    # Provide the balance for a given address
    if message.content.startswith('$balance'):
        address = str(message.content).split(' ')
        address.remove(testnet_name)
        address.remove('$balance')
        address = address[0]
        if len(address) == ADDRESS_LENGTH:
            balance = gaia.get_balance(testnet_name=testnet_name, address=address)
            if balance.keys():
                # await message.channel.send(f'{message.author.mention}\n' \
                await message.reply(f'Address `{address}` has a balance of ' \
                                        f'`{balance["amount"]}{balance["denom"]}`' \
                                        f'in testnet `{testnet_name}`')
            else:
                await message.reply(f'Account is not initialized (balance is empty)')
        else:
            await message.reply(f'Address must be {gaia.ADDRESS_LENGTH} characters long, received `{len(address)}`')
        return

    # Show node and faucet info
    if message.content.startswith('$faucet_status'):
        try:
            node_status = gaia.get_node_status(testnet_name=testnet_name)
            faucet_balance = gaia.get_balance(testnet_name=testnet_name, address=testnet["faucet"])

            if node_status.keys() and faucet_balance.keys():
                s = f'```\n' \
                    f'Node moniker:      {node_status["moniker"]}\n' \
                    f'Node catching up?  {node_status["syncs"]}\n' \
                    f'Node last block:   {node_status["last_block"]}\n' \
                    f'Faucet address:    {testnet["faucet"]}\n' \
                    f'Faucet balance:    {faucet_balance["amount"]}{faucet_balance["denom"]}' \
                    f'```'
                print(s)
                await message.reply(s)

        except Exception as statusErr:
            print(statusErr)
        return

    # Provide info on a specific transaction
    if message.content.startswith('$tx_info'):
        hash_id = str(message.content).split(' ')
        hash_id.remove(testnet_name)
        hash_id.remove('$tx_info')
        hash_id = hash_id[0]
        if len(hash_id) == 64:
            tx = gaia.get_tx_info(testnet_name=testnet_name, transaction=hash_id)
            if tx.keys():
                tx_info = f'```' \
                        f'From:    {tx["sender"]}\n' \
                        f'To:      {tx["recipient"]}\n' \
                        f'Amount:  {tx["amount"]}\n```'
            else:
                await message.reply("Could not obtain tx info")
            await message.reply(tx_info)
        else:
            await message.reply(f'Hash ID must be 64 characters long, received `{len(hash_id)}`')
        return

    # Send tokens to the specified address
    if message.content.startswith('$request'):
        print(message.content)
        channel = message.channel
        address = str(message.content).lower().split(" ")
        address.remove(testnet_name)
        address.remove('$request')
        address = address[0]

        if len(address) != ADDRESS_LENGTH or address[:len(ADDRESS_SUFFIX)] != ADDRESS_SUFFIX:
            await message.reply(f'Invalid address format: `{address}`:\n'
                               f'Address length must be `{ADDRESS_LENGTH}` and the suffix must be `{ADDRESS_SUFFIX}`')
            return

        # Check user allowance
        if requester.id in ACTIVE_REQUESTS[testnet_name]:
            check_time = ACTIVE_REQUESTS[testnet_name][requester.id]["next_request"]
            if check_time > message_timestamp:
                timeout_in_hours = int(REQUEST_TIMEOUT) / 60 / 60
                please_wait_text = f'You can request coins no more than once every {timeout_in_hours:.0f} hours, ' \
                                   f'please try again in ' \
                                   f'{round((check_time - message_timestamp) / 60, 2):.0f} minutes'
                await message.reply(please_wait_text)
                return

            else:
                del ACTIVE_REQUESTS[testnet_name][requester.id]
        
        # Check address allowance
        if address in ACTIVE_REQUESTS[testnet_name]:
            check_time = ACTIVE_REQUESTS[testnet_name][address]["next_request"]
            if check_time > message_timestamp:
                timeout_in_hours = int(REQUEST_TIMEOUT) / 60 / 60
                please_wait_text = f'You can request coins no more than once every {timeout_in_hours:.0f} hours, ' \
                                   f'please try again in ' \
                                   f'{round((check_time - message_timestamp) / 60, 2):.0f} minutes'
                await message.reply(please_wait_text)
                return

            else:
                del ACTIVE_REQUESTS[testnet_name][address]

        if requester.id not in ACTIVE_REQUESTS[testnet_name] and address not in ACTIVE_REQUESTS[testnet_name]:
            ACTIVE_REQUESTS[testnet_name][requester.id] = {
                 "requester": requester,
                 "next_request": message_timestamp + REQUEST_TIMEOUT}
            ACTIVE_REQUESTS[testnet_name][address] = {
                 "next_request": message_timestamp + REQUEST_TIMEOUT}


            balance = gaia.get_balance(testnet_name=testnet_name, address=address)
            print(balance)

            result = gaia.tx_send(testnet_name=testnet_name, recipient=address)

            if "coin_received" in result:
                for line in result.split('\n'):
                    if 'raw_log' in line:
                        line = line.replace("raw_log: '[", '')
                        line = line[:-2]
                        log = json.loads(line)
                        logger.info(f"{requester} had tokens sent to {address}.")
                        await message.reply("✅")
                        now = datetime.datetime.now()
                        await save_transaction_statistics(f'{now.strftime("%Y-%m-%d %H:%M:%S")}> {line}')
                balance = gaia.get_balance(testnet_name=testnet_name, address=address)
                print(balance)
            else:
                await message.reply(f'Could not send transaction, try making another request')
                del ACTIVE_REQUESTS[testnet_name][requester.id]
                del ACTIVE_REQUESTS[testnet_name][address]

client.run(DISCORD_TOKEN)