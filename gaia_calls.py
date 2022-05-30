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


def check_address(address: str):
    """
    gaiad keys parse <address>
    """
    check = subprocess.run(["gaiad", "keys", "parse",
                            f"{address}",
                            '--output=json'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True)
    try:
        check.check_returncode()
        return json.loads(check.stdout[:-1])
    except subprocess.CalledProcessError as cpe:
        output = str(check.stderr).split('\n', maxsplit=1)
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
                              f"--chain-id={chain_id}",
                              '--output=json'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        balance.check_returncode()
        return json.loads(balance.stdout)['balances']
    except subprocess.CalledProcessError as cpe:
        output = str(balance.stderr).split('\n', maxsplit=1)
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
        output = str(status.stderr).split('\n', maxsplit=1)
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
                              f'--chain-id={chain_id}',
                              '--output=json'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        tx_gaia.check_returncode()
        tx_response = json.loads(tx_gaia.stdout)
        tx_body = tx_response['tx']['body']['messages'][0]
        tx_out = {}
        tx_out['height'] = tx_response['height']
        if 'from_address' in tx_body.keys():
            tx_out['sender'] = tx_body['from_address']
            tx_out['receiver'] = tx_body['to_address']
            tx_out['amount'] = tx_body['amount'][0]['amount'] + \
                tx_body['amount'][0]['denom']
        elif 'sender' in tx_body.keys():
            tx_out['sender'] = tx_body['sender']
            tx_out['receiver'] = tx_body['receiver']
            tx_out['amount'] = tx_body['token']['amount'] + \
                tx_body['token']['denom']
        else:
            logging.error(
                "Neither 'from_address' nor 'sender' key was found in response body:\n%s", tx_body)
            return None
        return tx_out
    except subprocess.CalledProcessError as cpe:
        output = str(tx_gaia.stderr).split('\n', maxsplit=1)
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except (TypeError, KeyError) as err:
        logging.critical('Could not read %s in raw log.', err)
        raise KeyError from err


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
                              '--output=json',
                              '-y'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        tx_gaia.check_returncode()
        response = json.loads(tx_gaia.stdout)
        return response['txhash']
    except subprocess.CalledProcessError as cpe:
        output = str(tx_gaia.stderr).split('\n', maxsplit=1)
        logging.error("%s[%s]", cpe, output)
        raise cpe
    except (TypeError, KeyError) as err:
        output = tx_gaia.stderr
        logging.critical(
            'Could not read %s in tx response: %s', err, output)
        raise err
    return None
