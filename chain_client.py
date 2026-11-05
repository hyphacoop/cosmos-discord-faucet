"""
In-process Cosmos chain client for the faucet.

Builds, signs and broadcasts bank send transactions with cosmpy over gRPC,
so no chain binary is needed.

All methods block (cosmpy uses a synchronous gRPC client); call them from
async code through asyncio.to_thread.
"""

import threading
from typing import Optional

import bech32
from cosmpy.aerial.client import LedgerClient
from cosmpy.aerial.client.bank import create_bank_send_msg
from cosmpy.aerial.client.utils import prepare_and_broadcast_basic_transaction
from cosmpy.aerial.config import NetworkConfig
from cosmpy.aerial.tx import Transaction, TxFee
from cosmpy.aerial.types import Account
from cosmpy.aerial.wallet import LocalWallet
from cosmpy.crypto.address import Address

DEFAULT_GAS_LIMIT = 200000  # gaiad CLI default
# Account addresses are 20 bytes; module/contract/ICA addresses are 32 bytes
VALID_ADDRESS_LENGTHS = (20, 32)


class ChainError(Exception):
    """
    A query or transaction against the chain failed
    """


class ChainClient:
    """
    Signs and broadcasts faucet transfers for a single chain
    """

    def __init__(self, chain: dict):
        self.prefix = chain['prefix']
        self.denom = chain['denom']
        self.amount = int(chain['amount_to_send'])
        self.fee = f"{chain['tx_fees']}{chain['denom']}"
        self.gas_limit = int(chain.get('gas_limit', DEFAULT_GAS_LIMIT))

        self.client = LedgerClient(NetworkConfig(
            chain_id=chain['chain_id'],
            url=chain['grpc_url'],
            fee_minimum_gas_price=0,
            fee_denomination=self.denom,
            staking_denomination=self.denom,
        ))

        with open(chain['mnemonic_file'], 'r', encoding='utf-8') as key_file:
            mnemonic = ' '.join(key_file.read().split())
        self.wallet = LocalWallet.from_mnemonic(mnemonic, prefix=self.prefix)
        self._sender = self.wallet.address()
        self.address = str(self._sender)

        if self.address != chain['faucet_address']:
            raise ValueError(
                f'Mnemonic for {chain["chain_id"]} derives {self.address}, '
                f'but faucet_address is {chain["faucet_address"]}')

        # Serializes sends, since the account sequence is cached
        self._send_lock = threading.Lock()
        # Account number and next sequence; None means query the chain
        self._account: Optional[Account] = None

    def validate_address(self, address: str) -> Optional[str]:
        """
        Returns None if the address is valid for this chain,
        otherwise a short reason it was rejected
        """
        hrp, data = bech32.bech32_decode(address)
        if hrp is None or data is None:
            return 'Invalid address'
        if hrp != self.prefix:
            return f'Expected `{self.prefix}` prefix'
        decoded = bech32.convertbits(data, 5, 8, False)
        if decoded is None or len(decoded) not in VALID_ADDRESS_LENGTHS:
            return 'Invalid address'
        return None

    def get_faucet_balance(self) -> int:
        """
        Returns the faucet balance in the chain's denom
        """
        try:
            return self.client.query_bank_balance(self._sender, self.denom)
        except Exception as ex:
            raise ChainError(f'balance query failed: {ex}') from ex

    def send(self, recipient: str) -> str:
        """
        Sends amount_to_send to the recipient and returns the tx hash.
        Raises ChainError on failure.
        """
        with self._send_lock:
            try:
                if self._account is None:
                    self._account = self.client.query_account(self._sender)
                tx = Transaction()
                tx.add_message(create_bank_send_msg(
                    self._sender, Address(recipient), self.amount, self.denom))
                submitted = prepare_and_broadcast_basic_transaction(
                    self.client, tx, self.wallet, account=self._account,
                    fee=TxFee(amount=self.fee, gas_limit=self.gas_limit))
            except Exception as ex:
                # The sequence may be out of step with the chain; re-query next time
                self._account = None
                raise ChainError(f'send failed: {ex}') from ex
            self._account.sequence += 1
            return submitted.tx_hash
