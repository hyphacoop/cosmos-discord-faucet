"""
Tests for ChainClient.send sequence handling
"""

import unittest
from unittest import mock

from cosmpy.aerial.exceptions import BroadcastError
from cosmpy.aerial.types import Account

import chain_client
from chain_client import ChainClient, ChainError

MISMATCH = ('account sequence mismatch, expected 7672, got 7583: '
            'incorrect account sequence')


class SendTest(unittest.TestCase):
    """
    ChainClient.send keeps its cached sequence in step with the chain
    """

    def setUp(self):
        patches = {
            'LedgerClient': mock.patch.object(chain_client, 'LedgerClient'),
            'wallet': mock.patch.object(chain_client.LocalWallet, 'from_mnemonic'),
            'open': mock.patch('builtins.open', mock.mock_open(read_data='words')),
            'broadcast': mock.patch.object(
                chain_client, 'prepare_and_broadcast_basic_transaction'),
            'msg': mock.patch.object(chain_client, 'create_bank_send_msg'),
            'address': mock.patch.object(chain_client, 'Address'),
        }
        self.mocks = {name: p.start() for name, p in patches.items()}
        for patcher in patches.values():
            self.addCleanup(patcher.stop)

        self.mocks['wallet'].return_value.address.return_value = 'cosmos1faucet'
        self.client = ChainClient({
            'prefix': 'cosmos', 'denom': 'uatom', 'amount_to_send': '1000',
            'tx_fees': '1000', 'chain_id': 'test-1', 'grpc_url': 'grpc+http://x:9090',
            'mnemonic_file': 'm', 'faucet_address': 'cosmos1faucet',
        })
        self.query = self.client.client.query_account
        self.query.return_value = Account(address='cosmos1faucet', number=1, sequence=7583)
        self.broadcast = self.mocks['broadcast']
        # Record the sequence each broadcast was signed with
        self.signed = []

    def _broadcast_results(self, *results):
        results = iter(results)

        def fake(_client, _tx, _wallet, account, fee):  # pylint: disable=unused-argument
            self.signed.append(account.sequence)
            result = next(results)
            if isinstance(result, Exception):
                raise result
            return mock.Mock(tx_hash=result)
        self.broadcast.side_effect = fake

    def test_consecutive_sends_use_cached_sequence(self):
        """Back-to-back sends use N, N+1 without re-querying"""
        self._broadcast_results('HASH1', 'HASH2')
        self.assertEqual(self.client.send('cosmos1rcpt'), 'HASH1')
        self.assertEqual(self.client.send('cosmos1rcpt'), 'HASH2')
        self.assertEqual(self.signed, [7583, 7584])
        self.query.assert_called_once()  # pylint: disable=no-member

    def test_sequence_mismatch_resyncs_and_retries(self):
        """A mismatch resyncs to the expected sequence and retries once"""
        self._broadcast_results(BroadcastError('', MISMATCH), 'HASH')
        with self.assertLogs(chain_client.logger, 'WARNING'):
            self.assertEqual(self.client.send('cosmos1rcpt'), 'HASH')
        self.assertEqual(self.signed, [7583, 7672])
        self.assertEqual(self.client._account.sequence, 7673)  # pylint: disable=protected-access

    def test_repeated_mismatch_raises_and_resets(self):
        """A second mismatch gives up and clears the cache"""
        self._broadcast_results(BroadcastError('', MISMATCH), BroadcastError('', MISMATCH))
        with self.assertLogs(chain_client.logger, 'WARNING'), self.assertRaises(ChainError):
            self.client.send('cosmos1rcpt')
        self.assertEqual(len(self.signed), 2)
        self.assertIsNone(self.client._account)  # pylint: disable=protected-access

    def test_other_error_does_not_retry(self):
        """Other broadcast errors are not retried"""
        self._broadcast_results(BroadcastError('', 'insufficient funds'))
        with self.assertRaises(ChainError):
            self.client.send('cosmos1rcpt')
        self.assertEqual(len(self.signed), 1)
        self.assertIsNone(self.client._account)  # pylint: disable=protected-access


if __name__ == '__main__':
    unittest.main()
