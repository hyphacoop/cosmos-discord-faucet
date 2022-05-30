#!/usr/bin/env python
"""
Parses transaction log from faucet bot.
The reader expects the following CSV format:
ISO Date/Time,chain,address,amount sent,hash ID,faucet balance
For example:
2022-01-01T10:10:10,theta,cosmos123...xyz,10000uatom,12AB...90YZ,5000000uatom
"""

import csv
from datetime import datetime
import numpy as np


class TransactionReader():
    """
    Takes a CSV file for transactions and a logging period to check against.
    """

    def __init__(self,
                 filename: str = 'transactions.csv',
                 logging_period_seconds: int = 60):
        self._filename = filename
        self._txs = []
        self._stats = {}
        self._period = logging_period_seconds
        self._current_time = datetime.now()
        self._data = None
        self.read_transactions()
        self.process_stats()

    def stats(self):
        """
        Getter function for generated stats
        """
        return self._stats

    def is_new_data(self, date: str, time: str):
        """
        Expects 'YYYY-MM-DD' and 'HH:MM:SS' format.
        """
        record_timestamp = datetime.fromisoformat(date + 'T' + time)
        seconds_difference = abs((self._current_time -
                                  record_timestamp).total_seconds())
        if seconds_difference < self._period:
            return True
        return False

    def read_chains(self):
        """
        Prepare a dictionary for each chain found in the transaction log.
        """
        for chain in list(np.unique(self._data[:, 1])):
            self._stats[chain] = {
                'total_requests': 0,
                'recent_requests': 0,
                'total_accounts': 0,
                'recent_accounts': 0,
                'total_tokens': 0,
                'recent_tokens': 0,
                'faucet_balance': 0
            }

    def process_total_requests(self):
        """
        1. Total amount of requests made
        2. Total unique accounts seen
        3. Total amount of tokens sent
        """
        for chain in list(np.unique(self._data[:, 1])):
            mask = (self._data[:, 1] == chain)
            masked_chain = self._data[mask, :]
            self._stats[chain]['total_requests'] = len(masked_chain)
            self._stats[chain]['total_accounts'] = len(
                np.unique(masked_chain[:, 2]))
            token_array = np.array([int(token.replace('uatom', ''))
                                    for token in masked_chain[:, 3]])
            self._stats[chain]['total_tokens'] = np.sum(token_array)

    def process_recent_requests(self):
        """
        Read the data dictionary to save:
        1. Amount of requests made in the current logging period
        2. Unique accounts seen for the first time in the current logging period
        3. Amount of tokens seen in the current logging period
        """
        for chain in list(np.unique(self._data[:, 1])):
            chain_mask = (self._data[:, 1] == chain)
            chain_masked_array = self._data[chain_mask, :]

            time_deltas = [(self._current_time -
                            datetime.fromisoformat(stamp)).total_seconds()
                           for stamp in chain_masked_array[:, 0]]
            recent_tx_mask = np.array(time_deltas) < self._period
            old_tx_mask = np.array(time_deltas) >= self._period
            recent_txs = chain_masked_array[recent_tx_mask, :]
            old_txs = chain_masked_array[old_tx_mask, :]

            # Save all the recent requests
            self._stats[chain]['recent_requests'] = len(recent_txs)

            # Add up the unique accounts only if they were seen in the current logging period
            recent_unique_addrs = np.unique(recent_txs[:, 2])
            old_addrs = old_txs[:, 2]
            for addr in recent_unique_addrs:
                if addr not in old_addrs:
                    self._stats[chain]['recent_accounts'] += 1

            # Save the total tokens sent
            token_array = np.array([int(token.replace('uatom', ''))
                                    for token in recent_txs[:, 3]])
            self._stats[chain]['recent_tokens'] = np.sum(token_array)

    def process_balance(self):
        """
        Read the data dictionary to save:
        1. Last balance entry
        """
        for chain in list(np.unique(self._data[:, 1])):
            chain_mask = (self._data[:, 1] == chain)
            chain_masked_array = self._data[chain_mask, :]
            self._stats[chain]['faucet_balance'] = \
                int(chain_masked_array[-1][-1].replace('uatom', ''))

    def process_stats(self):
        """
        Processing is done sequentially to simplify logic and debugging.
        1. Populate the stats dictionary with the chains found in the transactions log
        2. Save the "total to date" metrics
        3. Save the "within the last period" metrics
        4. Save the current balance
        """
        self.read_chains()
        self.process_total_requests()
        self.process_recent_requests()
        self.process_balance()

    def read_transactions(self):
        """
        Parses the CSV file populating self._txs and self._stats
        """
        self._txs = []
        with open(self._filename, 'r', newline='', encoding='utf-8') as csvfile:
            data = list(csv.reader(csvfile, delimiter=','))
        self._data = np.array(data)
