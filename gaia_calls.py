import configparser
import json
import subprocess

c = configparser.ConfigParser()
c.read("config.ini", encoding='utf-8')

# Load data from config
VERBOSE_MODE = str(c["DEFAULT"]["verbose"])
BECH32_HRP = str(c["DEFAULT"]["BECH32_HRP"])
ADDRESS_LENGTH = 45
DENOM = str(c["DEFAULT"]["denomination"])
DECIMAL = float(c["DEFAULT"]["decimal"])
GAS_PRICE = float(c["TX"]["gas_price"])
GAS_LIMIT = float(c["TX"]["gas_limit"])
AMOUNT_TO_SEND = str(c["TX"]["amount_to_send"])+str(c["TX"]["denomination"])

VEGA_NODE = str(c["VEGA_TESTNET"]["node_url"])
VEGA_CHAIN = str(c["VEGA_TESTNET"]["chain_id"])
VEGA_FAUCET_ADDRESS = str(c["VEGA_TESTNET"]["faucet_address"])

THETA_NODE = str(c["THETA_TESTNET"]["node_url"])
THETA_CHAIN = str(c["THETA_TESTNET"]["chain_id"])
THETA_FAUCET_ADDRESS = str(c["THETA_TESTNET"]["faucet_address"])

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
    balance = subprocess.run(["gaiad", "query", "bank", "balances",
                              f"{address}",
                              f"--node={testnets[testnet_name]['node']}",
                              f"--chain-id={testnets[testnet_name]['chain']}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    faucet_balance = balance.stdout
    faucet_coins = {"amount": faucet_balance.split('\n')[1].split(' ')[2].split('"')[1],
                    "denom": faucet_balance.split('\n')[2].split(' ')[3]}
    return faucet_coins


def get_node_status(testnet_name: str):
    status = subprocess.run(
        ["gaiad", "status", f"--node={testnets[testnet_name]['node']}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    status = json.loads(status.stderr)
    node_status = {}
    node_status["moniker"] = status["NodeInfo"]["moniker"]
    node_status["chain"] = status["NodeInfo"]["network"]
    node_status["last_block"] = status["SyncInfo"]["latest_block_height"]
    node_status["syncs"] = status["SyncInfo"]["catching_up"]
    return node_status


def get_faucet_info(testnet_name: str):
    account = subprocess.run(["gaiad", "query", "account",
                              f"{testnets[testnet_name]['faucet']}",
                              f"--node={testnets[testnet_name]['node']}",
                              f"--chain-id={testnets[testnet_name]['chain']}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    account.stdout
    account_number = account_info.split('\n')[1].split(' ')[1]
    account_sequence = account_info.split('\n')[6].split(' ')[1]
    faucet_account = {"number": account_number,
                      "sequence": account_sequence}
    return faucet_account


def get_tx_info(testnet_name: str, transaction: str):
    try:
        tx = subprocess.run(["gaiad", "query", "tx",
                             f"{transaction}",
                             f"--node={testnets[testnet_name]['node']}",
                             f"--chain-id={testnets[testnet_name]['chain']}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        tx_response = tx.stdout
        tx_lines = tx_response.split('\n')
        for line in tx_lines:
            if 'raw_log' in line:
                line = line.replace("raw_log: '[", '')
                line = line[:-2]
                log = json.loads(line)
                transfer = log["events"][3]
                print(f"transfer: {transfer}")
                tx = {}
                tx["recipient"] = transfer["attributes"][0]["value"]
                tx["sender"] = transfer["attributes"][1]["value"]
                tx["amount"] = transfer["attributes"][2]["value"]
                return tx

    except Exception as tx_infoErr:
        print(tx_infoErr)


def tx_send(testnet_name: str, recipient: str):
    tx_send = subprocess.run(["gaiad", "tx", "bank", "send",
                              f"{testnets[testnet_name]['faucet']}",
                              f"{recipient}",
                              f"{AMOUNT_TO_SEND}",
                              f"--fees=500uatom",
                              f"--chain-id={testnets[testnet_name]['chain']}",
                              f"--keyring-backend=test",
                              f"--node={testnets[testnet_name]['node']}",
                              "-y"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return(tx_send.stdout)