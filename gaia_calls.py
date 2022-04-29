"""
gaiad utility functions
- query bank balance
- query tx
- node status
- tx bank send
"""

import json
import subprocess
import logging
import re


def check_address(address: str):
    """
    gaiad keys parse <address>
    """
    check = subprocess.run(["gaiad", "keys", "parse",
                            f"{address}"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True)
    try:
        check.check_returncode()
        address_dict = {entry.split(': ')[0]: entry.split(
            ': ')[1] for entry in check.stdout.split('\n')[:2]}
        return address_dict
    except subprocess.CalledProcessError as cpe:
        output = str(check.stderr).split('\n')[0]
        logging.error("Called Process Error: %s, stderr: %s", cpe, output)
        raise cpe
    except IndexError as index_error:
        logging.error('Parsing error on address check: %s', index_error)
        raise index_error
    return None


def get_balance(address: str, node: str, chain_id: str):
    """
    gaiad query bank balances <address> <node> <chain-id>
    """
    balance = subprocess.run(["gaiad", "query", "bank", "balances",
                              f"{address}",
                              f"--node={node}",
                              f"--chain-id={chain_id}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        balance.check_returncode()
        account_balance = balance.stdout
        balances = re.findall(r'amount: "[0-9]+"\n  denom: [a-z]+', account_balance)
        coins = []
        for balance in balances:
            denom = re.sub('amount:\s+"\d+"\n\s+denom:\s+','',balance)
            amount_leading_trim = re.sub('amount:\s+"','',balance)
            amount_string = re.sub('"\n\s+denom:\s+\w+','',amount_leading_trim, flags=re.IGNORECASE)
            coins.append({'amount': amount_string, 'denom': denom})
        return coins
    except subprocess.CalledProcessError as cpe:
        output = str(balance.stderr).split('\n')[0]
        logging.error("Called Process Error: %s, stderr: %s", cpe, output)
        raise cpe
    except IndexError as index_error:
        logging.error('Parsing error on balance request: %s', index_error)
        raise index_error
    return None


def get_node_status(node: str):
    """
    gaiad status <node>
    """
    status = subprocess.run(
        ['gaiad', 'status', f'--node={node}'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        status.check_returncode()
        status = json.loads(status.stderr)
        node_status = {}
        node_status['moniker'] = status['NodeInfo']['moniker']
        node_status['chain'] = status['NodeInfo']['network']
        node_status['last_block'] = status['SyncInfo']['latest_block_height']
        node_status['syncs'] = status['SyncInfo']['catching_up']
        return node_status
    except subprocess.CalledProcessError as cpe:
        output = str(status.stderr).split('\n')[0]
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except KeyError as key:
        logging.error('Key not found in node status: %s', key)
        raise key


def get_tx_info(hash_id: str, node: str, chain_id: str):
    """
    gaiad query tx <tx-hash> <node> <chain-id>
    """
    tx_gaia = subprocess.run(['gaiad', 'query', 'tx',
                              f'{hash_id}',
                              f'--node={node}',
                              f'--chain-id={chain_id}'],
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
                transfer = log['events'][3]
                tx_out = {}
                tx_out['recipient'] = transfer['attributes'][0]['value']
                tx_out['sender'] = transfer['attributes'][1]['value']
                tx_out['amount'] = transfer['attributes'][2]['value']
                return tx_out
        logging.error(
            "'raw_log' line was not found in response:\n%s", tx_response)
        return None
    except subprocess.CalledProcessError as cpe:
        output = str(tx_gaia.stderr).split('\n')[0]
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except (TypeError, KeyError) as err:
        logging.critical('Could not read %s in raw log: %s', err, log)
        raise KeyError


def tx_send(request: dict):
    """
    The request dictionary must include these keys:
    - "sender"
    - "recipient"
    - "amount"
    - "fees"
    - "node"
    - "chain_id"
    gaiad tx bank send <from address> <to address> <amount>
                       <fees> <node> <chain-id>
                       --keyring-backend=test -y

    """
    tx_gaia = subprocess.run(['gaiad', 'tx', 'bank', 'send',
                              f'{request["sender"]}',
                              f'{request["recipient"]}',
                              f'{request["amount"]}',
                              f'--fees={request["fees"]}',
                              f'--node={request["node"]}',
                              f'--chain-id={request["chain_id"]}',
                              '--keyring-backend=test',
                              '-y'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        tx_gaia.check_returncode()
        if 'coin_received' in tx_gaia.stdout:
            for line in tx_gaia.stdout.split('\n'):
                if 'txhash' in line:
                    return line.replace('txhash: ', '')
    except subprocess.CalledProcessError as cpe:
        output = str(tx_gaia.stderr).split('\n')[0]
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except (TypeError, KeyError) as err:
        output = tx_gaia.stderr
        logging.critical(
            'Could not read %s in tx response: %s', err, output)
        raise err
    return None
