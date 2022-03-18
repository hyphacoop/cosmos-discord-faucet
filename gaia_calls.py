"""
gaiad utility functions
- query account
- query bank balance
- query tx
- status
- tx bank send
"""

import configparser
import json
import subprocess
import logging
import sys

c = configparser.ConfigParser()
c.read("config.ini", encoding='utf-8')

# Load data from config
try:
    VERBOSE_MODE = str(c["DEFAULT"]["verbose"])
    BECH32_HRP = str(c["DEFAULT"]["BECH32_HRP"])
    ADDRESS_LENGTH = 45
    DENOM = str(c["DEFAULT"]["denomination"])
    DECIMAL = float(c["DEFAULT"]["decimal"])
    GAS_PRICE = float(c["TX"]["gas_price"])
    GAS_LIMIT = float(c["TX"]["gas_limit"])
    AMOUNT_TO_SEND = str(c["TX"]["amount_to_send"]) + \
        str(c["TX"]["denomination"])

    VEGA_NODE = str(c["VEGA_TESTNET"]["node_url"])
    VEGA_CHAIN = str(c["VEGA_TESTNET"]["chain_id"])
    VEGA_FAUCET_ADDRESS = str(c["VEGA_TESTNET"]["faucet_address"])

    THETA_NODE = str(c["THETA_TESTNET"]["node_url"])
    THETA_CHAIN = str(c["THETA_TESTNET"]["chain_id"])
    THETA_FAUCET_ADDRESS = str(c["THETA_TESTNET"]["faucet_address"])
except KeyError as key:
    logging.critical("Configuration could not be read for %s", key)
    sys.exit()

testnets = {
    "vega": {
        "node": VEGA_NODE,
        "chain": VEGA_CHAIN,
        "faucet": VEGA_FAUCET_ADDRESS
    },
    "theta": {
        "node": THETA_NODE,
        "chain": THETA_CHAIN,
        "faucet": THETA_FAUCET_ADDRESS
    },
}


def get_balance(testnet_name: str, address: str):
    # try:
    balance = subprocess.run(["gaiad", "query", "bank", "balances",
                              f"{address}",
                              f"--node={testnets[testnet_name]['node']}",
                              f"--chain-id={testnets[testnet_name]['chain']}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, check=True)
    # try:
    # balance.check_returncode()
    account_balance = balance.stdout
    print(account_balance)
    faucet_coins = {"amount": account_balance.split('\n')[1].split(' ')[2].split('"')[1],
                    "denom": account_balance.split('\n')[2].split(' ')[3]}
    return faucet_coins
    # except subprocess.CalledProcessError as cpe:
    #     output = str(balance.stderr).split('\n')[0]
    #     logging.error("%s[%s]", cpe, output)
    #     raise cpe
    # except IndexError as index_error:
    #     logging.error("Parsing error on balance request: %s", index_error)
    #     raise index_error
    # except Exception as exc:
    #     print(exc)
    return None


def get_node_status(testnet_name: str):
    status = subprocess.run(
        ["gaiad", "status", f"--node={testnets[testnet_name]['node']}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        status.check_returncode()
        status = json.loads(status.stderr)
        node_status = {}
        node_status["moniker"] = status["NodeInfo"]["moniker"]
        node_status["chain"] = status["NodeInfo"]["network"]
        node_status["last_block"] = status["SyncInfo"]["latest_block_height"]
        node_status["syncs"] = status["SyncInfo"]["catching_up"]
        return node_status
    except subprocess.CalledProcessError as cpe:
        output = str(status.stderr).split('\n')[0]
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except KeyError as key:
        logging.error("Key not found in node status: %s", key)
        raise key


def get_faucet_info(testnet_name: str):
    # Currently not being used
    account_info = subprocess.run(["gaiad", "query", "account",
                                   f"{testnets[testnet_name]['faucet']}",
                                   f"--node={testnets[testnet_name]['node']}",
                                   f"--chain-id={testnets[testnet_name]['chain']}"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    account_number = account_info.stdout.split('\n')[1].split(' ')[1]
    account_sequence = account_info.stdout.split('\n')[6].split(' ')[1]
    faucet_account = {"number": account_number,
                      "sequence": account_sequence}
    return faucet_account


def get_tx_info(testnet_name: str, transaction: str):
    tx_gaia = subprocess.run(["gaiad", "query", "tx",
                              f"{transaction}",
                              f"--node={testnets[testnet_name]['node']}",
                              f"--chain-id={testnets[testnet_name]['chain']}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        tx_gaia.check_returncode()
        tx_response = tx_gaia.stdout
        tx_lines = tx_response.split('\n')
        for line in tx_lines:
            if 'raw_log' in line:
                line = line.replace("raw_log: '[", '')
                line = line[:-2]
                log = json.loads(line)
                transfer = log["event"][3]
                tx_out = {}
                tx_out["recipient"] = transfer["attributes"][0]["value"]
                tx_out["sender"] = transfer["attributes"][1]["value"]
                tx_out["amount"] = transfer["attributes"][2]["value"]
                return tx_out
        logging.error(
            "'raw_log' line was not found in response:\n%s", tx_response)
        return None
    except subprocess.CalledProcessError as cpe:
        output = str(tx_gaia.stderr).split('\n')[0]
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except (TypeError, KeyError) as err:
        logging.critical("Could not read %s in raw log: %s", err, log)
        raise KeyError


def tx_send(testnet_name: str, recipient: str):
    tx_gaia = subprocess.run(["gaiad", "tx", "bank", "send",
                              f"{testnets[testnet_name]['faucet']}",
                              f"{recipient}",
                              f"{AMOUNT_TO_SEND}",
                              "--fees=500uatom",
                              f"--chain-id={testnets[testnet_name]['chain']}",
                              "--keyring-backend=test",
                              f"--node={testnets[testnet_name]['node']}",
                              "-y"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        tx_gaia.check_returncode()
        if "coin_received" in tx_gaia.stdout:
            for line in tx_gaia.stdout.split('\n'):
                if 'raw_log' in line:
                    line = line.replace("raw_log: '[", '')
                    line = line[:-2]
                    log = json.loads(line)
                    return log["events"][3]["attributes"]
    except subprocess.CalledProcessError as cpe:
        output = str(tx_gaia.stderr).split('\n')[0]
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except (TypeError, KeyError) as err:
        output = tx_gaia.stderr
        logging.critical(
            "Could not read %s in tx response: %s", err, output)
        raise err
    return None
