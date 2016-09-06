#! /usr/bin/env python3
"""
A convenience script for displaying the input/output pairing of JMTXs.
Can read JM TX IDs from an input file, or 
"""

from argparse import ArgumentParser

from jm_unmixer.btccommon import gen_txids_from_cli_args
from jm_unmixer.jmtx import JoinMarketTx, Unpairable

###############################################################################

def main():
    
    args = getopt()

    for txid in gen_txids_from_cli_args(args.txid):
        txid = txid.strip()
        if not txid:
            continue
        print(txid)
        try:
            tx = JoinMarketTx.from_id(txid)
            print(tx.describe_inout_value_pairs())
        except Unpairable as e:
            print('UNPAIRABLE (%s)' % (e,))
        print()

###############################################################################

def getopt():
    parser = ArgumentParser()
    parser.add_argument('txid', nargs = '*')
    return parser.parse_args()

###############################################################################

if __name__ == '__main__':
    main()
