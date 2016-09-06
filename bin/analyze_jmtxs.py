#! /usr/bin/env python3
"""
Run the JM unmixing analysis, by linking maker-inputs with outputs of previous
JMTXs.
This script prints statistics about analysis results, and optionally dumps
JMTX data (together with their "taint" data) to a file.
"""

import pickle
import numpy as np
from collections import OrderedDict
from argparse import ArgumentParser

from jm_unmixer.misc import gzopen, iter_pkl_list, progressbar, map_with_progressbar
from jm_unmixer.jmtx import UnmixedJoinMarketTx, get_vout_addresses

###############################################################################
# functions

def extract_maker_addresses(jmtxs, num_workers = 1):
    tx_addresses_list = map_with_progressbar(extract_maker_addresses_from_tx, jmtxs.values(), num_workers = num_workers)
    addresses = set()
    for tx_addresses in tx_addresses_list:
        addresses.update(tx_addresses)
    return addresses

def extract_maker_addresses_from_tx(jmtx):
    addresses = set()
    vin_values = list(jmtx.vin_values)
    for maker_pair in jmtx.maker_value_pairs:
        for value in maker_pair[0]:
            i = vin_values.index(value)
            vin_values[i] = None
            vin = jmtx.vin[i]
            back_vout = jmtx.get_vout_being_spent_by_vin(vin)
            for addr in get_vout_addresses(back_vout):
                assert 30 <= len(addr) <= 36, addr
                addresses.add(addr)
    return addresses

def mark_makers(jmtxs, maker_address_set):
    with progressbar(jmtxs.items()) as ITEMS:
        tjmtxs = OrderedDict()
        for txid, tx in ITEMS:
            ttx = UnmixedJoinMarketTx(tx)
            for vout in tx.vout:
                vout_addrs = get_vout_addresses(vout)
                vout_maker_addrs = maker_address_set & set(vout_addrs)
                # if there are maker addresses in this vout, then all addresses in this vout are maker addresses
                if vout_maker_addrs:
                    for addr in vout_addrs:
                        ttx.add_maker_address(addr)
            tjmtxs[txid] = ttx
        return tjmtxs

def get_unmix_levels(tjmtxs, num_workers = 1):
    return list(map_with_progressbar(get_unmix_level, tjmtxs, num_workers = num_workers))

def get_unmix_level(tx):
    return tx.unmix_level

def get_all_jmtxs(infiles):
    txs = OrderedDict()
    for infile in infiles:
        for tx in iter_pkl_list(infile):
            txs[tx.id] = tx
    return txs

def print_summary(tjmtxs, unmix_levels_raw):
    unmix_levels = np.array([ uml for uml in unmix_levels_raw if uml is not None ])

    print('NUM JMTXS: %s' % len(tjmtxs))
    print('NUM JMTXS WITH UNMIX LEVEL: %s' % (len(unmix_levels)))
    print('AVG UNMIX LEVEL:     %.2f' % (np.mean(unmix_levels)))
    print('MEDIAN UNMIX LEVEL:  %.2f' % (np.median(unmix_levels)))
    print('MIN UNMIX LEVEL:     %.2f' % (np.min(unmix_levels)))
    print('MAX UNMIX LEVEL:     %.2f' % (np.max(unmix_levels)))
    print('FULLY UNMIXED FRAC:  %.2f' % (np.sum(unmix_levels == 1) / float(len(unmix_levels))))

###############################################################################
# MAIN

def main():
    
    args = getopt()
    
    # read all jmtxs
    print('READING JMTXS')
    jmtxs = get_all_jmtxs(args.infiles)
    print('%d jmtxs found' % ( len(jmtxs), ))
    if args.num_txs:
        jmtxs = OrderedDict(list(jmtxs.items())[-args.num_txs:])
        print('%d jmtxs to process (quick mode)' % ( len(jmtxs), ))
    
    # pass1: remember all makers
    print('PASS 1: LINKING')
    maker_address_set = extract_maker_addresses(jmtxs, num_workers = args.num_workers)
    print('%d maker addresses extracted from %d jmtxs' % ( len(maker_address_set), len(jmtxs), ))
    
    # pass2: mark jmtx outputs as makers
    print('PASS 2: UNMIXING')
    tjmtxs = mark_makers(jmtxs, maker_address_set)

    print('PASS 3: CALCULATING UNMIX LEVELS')
    unmix_levels = get_unmix_levels(tjmtxs.values(), num_workers = args.num_workers)

    # dump to a file
    if args.outfile:
        print('writing outfile to: %s' % args.outfile)
        with gzopen(args.outfile, 'wb') as F:
            pickle.dump(( tjmtxs, unmix_levels, maker_address_set ), F)
    
    # stats and output:
    print('STATS')
    print_summary(tjmtxs, unmix_levels)

###############################################################################

def getopt():
    parser = ArgumentParser()
    parser.add_argument('infiles', nargs = '+')
    parser.add_argument('-o', '--outfile')
    parser.add_argument('-w', '--num-workers', type = int, default = 8)
    parser.add_argument('-z', '--num-txs', type = int, help = 'quick mode to limit number of txs processed, for debugging')
    return parser.parse_args()

###############################################################################

if __name__ == '__main__':
    main()
