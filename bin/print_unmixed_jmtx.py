#! /usr/bin/env python3
"""
Prints the details of an unmixed JMTX, including which inputs/outputs belong to
makers, which belong to the taker, and the links to other JMTXs which were exploited
in order to unmix this JMTX.
"""

from collections import OrderedDict
import pickle
import numpy as np
from argparse import ArgumentParser

from jm_unmixer.misc import gzopen
from jm_unmixer.jmtx import get_vout_addresses


###############################################################################
# functions

def describe_tx(tjmtx, tjmtxs, maker_address_set):

    print('=' * 80)
    print('TRANSACTION UNMIXED:')
    print('=' * 80)
    print('%s' % short_tx_repr(tjmtx))
    print()
    print(tjmtx.describe_inout_value_pairs())
    print()
    print('POSSIBLE TAKER ADDRESSES:')
    for addrs in tjmtx.possible_taker_mix_addresses:
        for addr in addrs:
            print('    %s' % addr)
    print('KNOWN MAKER ADDRESSES:')
    for addr in tjmtx.maker_addresses:
        print('    %s' % addr)
    print()
    
    spending_data_per_addr = {}
    for tx in tjmtxs.values():
        for vin_idx, vin in enumerate(tx.vin):
            spending_data_per_addr[vin['txid'], vin['vout']] = ( tx.id, vin_idx )
    
    spending_info = OrderedDict()
    for vout_idx, vout in enumerate(tjmtx.vout):
        value = vout['value']
        if value != tjmtx.value_mixed:
            continue
        vout_addrs = get_vout_addresses(vout)
        vout_maker_addrs = set(vout_addrs) & maker_address_set
        if vout_maker_addrs:
            print('MAKER ADDRESSES: %s' % ' '.join(vout_maker_addrs))
            spending_txid, vin_idx = spending_data_per_addr[tjmtx.id, vout_idx]
            spending_info.setdefault(spending_txid, []).append(( vout_maker_addrs, value ))
            print('  %.4f btc is spent from tx %s, vout #%s' %( value, spending_txid, vout_idx))
        else:
            print('TAKER: %s' % ' '.join(vout_addrs))

    print()
    print()
    print('=' * 80)
    print('TRANSACTIONS EXPLOITED:')
    print('=' * 80)
    print()
    for txid, maker_values in spending_info.items():
        tx = tjmtxs[txid]
        print('%s' % short_tx_repr(tx))
        print(tx.describe_inout_value_pairs())
        print('Values exploited:')
        for maker_addrs, value in maker_values:
            print('  %.4f btc is spent from addr %s' % (value, ', '.join(maker_addrs)))
        print()
        print()
    
def choose_tx(tjmtxs, unmix_levels, max_parties = 1000):
    umls = np.array([ uml if uml is not None else 0. for uml in unmix_levels ])
    parties = np.array([ tx.num_parties for tx in tjmtxs.values() ])
    grade = umls**2 * parties
    grade[parties > max_parties] = -1
    idx = len(grade)-1 - np.argmax(grade[::-1])
    tx = list(tjmtxs.values())[idx]
    print('choosing tx: %s (uml=%s, parties=%s)' % (tx.id, umls[idx], parties[idx]))
    assert tx.unmix_level == umls[idx]
    assert tx.num_parties == parties[idx]
    return tx

def short_tx_repr(tx):
    x = repr(tx).strip('<>')
    return ' '.join(['Tx'] + x.split()[1:])

###############################################################################
# MAIN

def main():
    
    args = getopt()
    
    with gzopen(args.infile, 'rb') as F:
        tjmtxs, unmix_levels, maker_address_set = pickle.load(F)
        
    txid = args.tx
    if txid:
        tjmtx = tjmtxs[txid]
    else:
        tjmtx = choose_tx(tjmtxs, unmix_levels, max_parties = args.max_parties)

    describe_tx(tjmtx, tjmtxs, maker_address_set)
    
###############################################################################

def getopt():
    parser = ArgumentParser()
    parser.add_argument('-i', '--infile', required = True, help = 'The unmixing-data pkl file dumped by analyze_jmtxs.py')
    parser.add_argument('--tx', help = 'run on this TX, instead of automatically choosing one')
    parser.add_argument('--max-parties', type = int, default = 1000)
    return parser.parse_args()

###############################################################################

if __name__ == '__main__':
    main()
