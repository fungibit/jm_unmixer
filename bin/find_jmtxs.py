#! /usr/bin/env python3
"""
Scan blockchain transactions, and find JM transactions.
This script prints JMTXs IDs, and optionally dumps them to a pickle file.
"""

import os
from argparse import ArgumentParser

from jm_unmixer.misc import pkl_append, map_with_progressbar
from jm_unmixer.btccommon import BLOCKCHAIN, Block, Tx, reconnect
from jm_unmixer.jmtx import to_joinmarket_tx, Unpairable

###############################################################################
# functions

ARG_TYPE_BLOCK_ID = 0
ARG_TYPE_BLOCK_HEIGHT = 1
ARG_TYPE_TX_ID = 2
ARG_TYPE_FILE = 3

def gen_txids_from_args(args, num_workers):
    arg_types = set([ get_arg_type(arg) for arg in args ])
    if len(arg_types) > 1:
        raise ValueError('bad usage: ambiguous arg types (%s)' % arg_types)
    arg_type, = arg_types
    if arg_type == ARG_TYPE_BLOCK_ID:
        for bid in args:
            block = Block(BLOCKCHAIN.get_block_by_id(bid))
            #print('# starting block %s' % block.height)
            yield from block.txids
            #print('# finished block %s' % block.height)
    elif arg_type == ARG_TYPE_BLOCK_HEIGHT:
        h1 = int(args[0])
        if len(args) == 1:
            hs = [ h1 ]
        elif len(args) == 2:
            h2 = int(args[1])
            hs = range(h1, h2)
        else:
            raise ValueError('Block heights should pe passed as a start/end range')
        txids = []
        block_txids_gen = map_with_progressbar(get_block_txids, hs, num_workers = num_workers, preserve_order = False)
        for block_txids in block_txids_gen:
            txids.extend(block_txids)
        yield from txids
    elif arg_type == ARG_TYPE_TX_ID:
        yield from args
    elif arg_type == ARG_TYPE_FILE:
        for fn in args:
            with open(fn) as f:
                for line in f:
                    txid = line.strip()
                    if txid:
                        yield txid

def get_block_txids(height):
    block = Block(BLOCKCHAIN.get_block_by_height(height))
    return block.txids

def get_arg_type(arg):
    
    if os.path.exists(arg):
        return ARG_TYPE_FILE
    
    if len(arg) == 64:
        if arg.startswith('0000000'):
            return ARG_TYPE_BLOCK_ID
        else:
            return ARG_TYPE_TX_ID
    try:
        if int(arg) < 10**9:
            return ARG_TYPE_BLOCK_HEIGHT
    except TypeError:
        pass
    
    raise ValueError('Arg not understood: %s' % arg)

###############################################################################

pid_of_connection = os.getpid()

def process_tx(txid):
    
    global pid_of_connection
    if os.getpid() != pid_of_connection:
        reconnect()
        pid_of_connection = os.getpid()
    
    tx = Tx.from_id(txid)
    try:
        return to_joinmarket_tx(tx)
    except Unpairable:
        return None

###############################################################################
# MAIN

def main():
    
    args = getopt()
    
    print('collecting txids...')
    txids = list(gen_txids_from_args(args.args, num_workers = args.num_workers))
    print('%d txs found' % (len(txids)))
    print('looking for jmtxs...')
    jmtx_gen = map_with_progressbar(process_tx, txids, num_workers = args.num_workers, preserve_order = False)
    jmtxs = list(jmtx_gen)
    for jmtx in jmtxs:
        if jmtx is None:
            continue
        print('JMTX %s' % ( jmtx.id, ))
        if args.outfile:
            pkl_append(args.outfile, jmtx)

###############################################################################

def getopt():
    parser = ArgumentParser()
    parser.add_argument('args', nargs = '+', help = 'either: tx IDs, block IDs, a range of block heights, or filename containing tx IDs')
    parser.add_argument('-w', '--num-workers', type = int, default = 8)
    parser.add_argument('-o', '--outfile')
    return parser.parse_args()

###############################################################################

if __name__ == '__main__':
    main()
