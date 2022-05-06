#!/usr/bin/env python
"""
Parses transactions and writes to a
Node Exporter file periodically.
Usage:
python cosmos_faucet_analytics.py [transaction log file] [node exporter textfile] [period in seconds]
Example:
python cosmos_faucet_analytics.py transactions.csv /opt/node_exporter/textfiles/faucet_stats.prom 60
Outputs per chain:
- Total requests to date.
- Requests made in the last reporting period.
- Unique addresses to date.
- Unique addresses in the last reporting period.
- uatom sent to date.
- uatom sent in the last reporting period.
- Faucet balance.
"""

import sys
from time import sleep
from cosmos_transaction_reader import TransactionReader


class FaucetAnalytics():
    """
    Logs faucet stats
    """

    def __init__(self,
                 txs_filename: str = '~/cosmos-discord-faucet/transactions.csv',
                 prom_filename: str = '/opt/node_exporter/' +
                 'textfiles/FAUCET_STATS.prom',
                 seconds_to_update: int = 60):
        self._faucets_dict = {}
        self._txs_filename = txs_filename
        self._prom_filename = prom_filename
        self._period = seconds_to_update
        self._prefix = 'FAUCET_STATS'

    def timer_timeout(self):
        """
        Updates .prom file regularly.
        """
        reader = TransactionReader(filename=self._txs_filename,
                                   logging_period_seconds=self._period)
        self._faucets_dict = reader.stats()
        with open(self._prom_filename, 'w', encoding='utf-8') as log_file:
            lines = []
            for chain, stats in self._faucets_dict.items():
                for stat, value in stats.items():
                    line = self._prefix + '{src="' + \
                        f'{chain}_' + \
                        f'{stat}"' + '} ' + \
                        f'{value}\n'
                    lines.append(line)
            log_file.writelines(lines)

    def start(self):
        """
        Starts main loop
        """
        while True:
            self.timer_timeout()
            sleep(self._period)


if __name__ == '__main__':
    args = sys.argv
    if len(args) > 3:
        logger = FaucetAnalytics(txs_filename=args[1],
                                   prom_filename=args[2],
                                   seconds_to_update=int(args[3]))
        logger.start()
