"""
Representation and basic analysis (input/output pairing) of JM transactions.
"""

from decimal import Decimal
from collections import Counter
from itertools import zip_longest, combinations
import numpy as np

from .misc import memoized_property
from .btccommon import Tx

################################################################################
# Constants

MIN_NUM_INPUTS = 3
MIN_NUM_OUTPUTS = 3

MIN_JM_FEE = 0.000001
MAX_JM_FEE = 0.03
MIN_MIX_VALUE = Decimal('0.01')
#MIN_JM_RAW_TX_SIZE = 1500  # raw-size of a jmtx can't be smaller than this

class Unpairable(Exception):
    pass

################################################################################

class JoinMarketTx(Tx):
    
    def __init__(self, json, pairs, *args, **kwargs):
        try:
            json = json.json
        except AttributeError:
            pass
        self.pairs = pairs
        super(JoinMarketTx, self).__init__(json, *args, **kwargs)

    @classmethod
    def from_tx(cls, tx):
        return to_joinmarket_tx(tx)

    @classmethod
    def from_json(cls, json):
        return cls.from_tx(Tx(json))
    
    @classmethod
    def from_id(cls, id, *args, **kwargs):
        return cls.from_tx(Tx.from_id(id))
    
    @memoized_property
    def value_mixed(self):
        values = set(self.pairs[0][1])
        for pair in self.pairs[1:]:
            values = values & set(pair[1])
        x, = values
        return x

    @property
    def mixed_vouts(self):
        return [ vout for vout in self.vout if vout['value'] == self.value_mixed ]

    @property
    def num_parties(self):
        return len(self.pairs)

    @property
    def taker_value_pair(self):
        return [ p for p in self.pairs if float(fee_paid_by_pair(p)) > 0 ][0]

    @property
    def maker_value_pairs(self):
        return [ p for p in self.pairs if float(fee_paid_to_pair(p)) >= 0 ]

    @property
    def taker_input_values(self):
        return self.taker_value_pair[0]
    
    @property
    def taker_output_values(self):
        return self.taker_value_pair[1]
    
    @property
    def txfee(self):
        return sum(sum(p[0]) for p in self.pairs) - sum(sum(p[1]) for p in self.pairs)
    
    @property
    def total_jm_fee(self):
        taker_pair = self.taker_value_pair
        total_taker_fee = sum(taker_pair[0]) - sum(taker_pair[1])
        return total_taker_fee - self.txfee

    def describe_inout_value_pairs(self):
        value_mixed = self.value_mixed
        fmt = lambda pair, pref=None: self._format_value(pair, pref)
        lines = []
        # taker
        lines.append('[TAKER]')
        lines.extend(self._describe_pair(self.taker_value_pair, 0, value_mixed))
        lines.append('  %s  %s' % (fmt('(JMFEE=%s)' % self.total_jm_fee), fmt(None)))
        lines.append('  %s  %s' % (fmt('(TXFEE=%s)' % self.txfee), fmt(None)))
        # makers
        for pidx, pair in enumerate(self.maker_value_pairs):
            lines.append('[MAKER %s]' % pidx)
            lines.extend(self._describe_pair(pair, pidx + 1, value_mixed))
            maker_fee = fee_paid_to_pair(pair)
            lines.append('  %s  %s' % (fmt(None), fmt('(JMFEE=%s)' % maker_fee)))
            #lines.append('')
        return '\n'.join(lines)
    
    def _describe_pair(self, pair, pidx, value_mixed):
        fmt = lambda pair, pref, value = None: self._format_value(pair, pref, value == value_mixed)
        lines = []
        cur_inputs, cur_outputs = pair
        for i, o in zip_longest(cur_inputs, cur_outputs):
            lines.append('  %s  %s' % (fmt(i, 'IN '), fmt(o, 'OUT')))
        return lines
    
    def _format_value(self, v, pref, add_mark = False):
        suffix = ' **' if add_mark else ''
        pref = '%s: ' % pref if pref is not None else ''
        return ' '*23 if v is None else '%s%18s%s' % ( pref, v, suffix)
    
    def __repr__(self):
        x = super().__repr__()
        extra = '{%dx %.3f btc, %s->%s inouts}' % (
            len(self.pairs), self.value_mixed, len(self.vin), len(self.vout))
        return '%s %s%s' % ( x[:-1], extra , x[-1:] )

class UnmixedJoinMarketTx(JoinMarketTx):
    
    def __init__(self, jmtx, maker_addresses = ()):
        super(UnmixedJoinMarketTx, self).__init__(jmtx.json, jmtx.pairs)
        self.maker_addresses = set(maker_addresses)

    def add_maker_address(self, addr):
        self.maker_addresses.add(addr)

    @property
    def possible_taker_mixed_vouts(self):
        return [
            vout for vout in self.mixed_vouts
            if not (self.maker_addresses & set(get_vout_addresses(vout)))
        ]

    @property
    def possible_taker_mix_addresses(self):
        return [ get_vout_addresses(vout) for vout in self.possible_taker_mixed_vouts ]
    
    @property
    def unmix_level(self):
        # [0,1] where 0 is perfect mix and 1 is completely unmixed.
        # e.g. in a 8-party jmtx, if we know 7 makers, it is completely unmixed.
        possible_takers = len(self.possible_taker_mixed_vouts)
        if possible_takers == 0:
            #print('%s: no takers' % self.id)
            return None
        possible_makers = self.num_parties - possible_takers
        return possible_makers / (self.num_parties - 1)

################################################################################
# Useful functions for working with jmtxs
################################################################################

def check_potential_joinmarket_tx(tx):
    # a quick trivial-reject check
    
    num_inputs = len(tx.vin)
    num_outputs = len(tx.vout)
    
    if num_outputs <= MIN_NUM_OUTPUTS:
        return False, 'MIN_NUM_OUTPUTS'
    if num_inputs <= MIN_NUM_INPUTS:
        return False, 'MIN_NUM_INPUTS'
    value_mixed, count = get_value_mixed(tx)
    if value_mixed is None:
        return False, 'no value_mixed'
    if value_mixed < MIN_MIX_VALUE:
        return False, 'MIN_MIX_VALUE'
    # a JMTX, in addition to N equal outputs, has a change output for each maker,
    # and optionally a change output for the taker:
    if not (2*count-1 <= num_outputs <= 2*count):
        return False, 'UNUSUAL NUMBER OF OUTPUTS'

    # avoid processing insane transactions
    if num_inputs > 25:
        return False, 'TOO MANY INPUTS'

    return True, ''

def to_joinmarket_tx(tx, *args, **kwargs):
    if isinstance(tx, str):
        tx = Tx.from_id(tx)

    is_ok, desc = check_potential_joinmarket_tx(tx)
    if not is_ok:
        raise Unpairable(desc)

    # pair up!
    vin_values = tx.vin_values
    vout_values = tx.vout_values
    pairs = pair_up_inout_values(vin_values, vout_values)  # can raise Unpairable

    return JoinMarketTx(tx, pairs, *args, **kwargs)

def get_value_mixed(tx):
    return get_value_mixed_from_values(tx.vin_values, tx.vout_values)

def get_value_mixed_from_values(in_values, out_values):
    output_values_counter = Counter(out_values)
    common_output_value, common_output_value_count = output_values_counter.most_common(1)[0]
    output_values_counter.pop(common_output_value)
    if common_output_value_count <= 2:
        # 2 meaning 2-party coinjoin, which is unlikely because it has little value
        return None, None
    if output_values_counter:
        v2, v2_count = output_values_counter.most_common(1)[0]
        if v2_count == common_output_value_count:
            return None, None
    return common_output_value, common_output_value_count

def fee_paid_to_pair(pair):
    return sum(pair[1]) - sum(pair[0])

def fee_paid_by_pair(pair):
    return -fee_paid_to_pair(pair)

def get_vout_addresses(vout):
    return vout['scriptPubKey']['addresses']


################################################################################
# The JM inputs/outputs pairing algorithm
################################################################################

def pair_up_inout_values(in_values, out_values, value_mixed = None):
    if value_mixed is None:
        value_mixed = get_value_mixed_from_values(in_values, out_values)[0]
    pairs = _pair_up_inout_values(in_values, out_values, value_mixed = value_mixed)
    return pairs
    
def _pair_up_inout_values(in_values, out_values, value_mixed = None):

    # split outputs to mix_values and change_values
    in_values = list(in_values)
    change_values = list(out_values)
    mix_values = []
    while True:
        try:
            change_values.remove(value_mixed)
            mix_values.append(value_mixed)
        except ValueError:
            break
    change_values.sort()
    num_parties = len(mix_values)
    
    txfee = sum(in_values) - sum(out_values)
    assert txfee >= 0, txfee
    
    # we look for input groups of size i to match any of the outputs.
    # note we only match makers here, not the taker (which has to be matched last).
    assert num_parties-1 <= len(change_values) <= num_parties, (num_parties, len(change_values))
    pairs = []
    num_pairs_left = num_parties
    cur_max_jmfee = 16*MIN_JM_FEE
    bucket_sizes = range(1, len(in_values) - num_pairs_left + 2)
    dists = MIN_JM_FEE * 2**np.arange(4, 40)
    dists = dists[dists < MAX_JM_FEE]
    while num_pairs_left > 1:
        found_new_pair = False
        for bucket_size, cur_max_jmfee in gen_bucket_size_dist_pairs(bucket_sizes, dists):
            #print('XXX %s %s' % (bucket_size, cur_max_jmfee))
            for iidxs in combinations(range(len(in_values)), bucket_size):
                sum_bucket_input = sum( in_values[iidx] for iidx in iidxs )
                min_dist = cur_max_jmfee
                min_dist_cidx = -1
                for cidx, change_value in enumerate(change_values):
                    dist = change_value + value_mixed - sum_bucket_input
                    if MIN_JM_FEE < dist < min_dist:
                        min_dist = dist
                        min_dist_cidx = cidx
                if min_dist_cidx >= 0:
                    # found a pair
                    cur_inputs = []
                    for iidx in reversed(iidxs):
                        cur_inputs.append(in_values[iidx])
                        in_values = in_values[:iidx] + in_values[iidx+1:]
                    cur_outputs = [ mix_values.pop(), change_values[min_dist_cidx] ]
                    change_values = change_values[:min_dist_cidx] + change_values[min_dist_cidx+1:]
                    pairs.append([ cur_inputs, cur_outputs ])
                    num_pairs_left -= 1
                    #print('pair found: max_jmfee=%.7f bucket=%s pairs_left=%s inputs_left=%s' % (cur_max_jmfee, bucket_size, num_pairs_left, len(in_values)))
                    # starting over this bucket size
                    found_new_pair = True
                    break
            if found_new_pair:
                # found -- start over, with smaller inputs
                break
        else:
            # done, not found anything -- abort
            break
    
    if num_pairs_left == 1:
        # only taker is left
        assert len(mix_values) == num_pairs_left, (len(mix_values), num_pairs_left)
        sum_inputs = sum(in_values)
        sum_outputs = sum(change_values) + sum(mix_values)
        total_jmfee = sum_inputs - sum_outputs - txfee
        if not MIN_JM_FEE < total_jmfee / (num_parties-1) < MAX_JM_FEE:
            raise Unpairable('taker fees dont add up')
        pair = [ in_values, mix_values + change_values ]
        pairs = [ pair ] + pairs
        in_values = []
        change_values = []
        mix_values = []

    if mix_values or in_values or change_values:
        raise Unpairable('unpairable change values: %s' % change_values)

    return pairs

def gen_bucket_size_dist_pairs(bucket_sizes, dists):
    DIST_PENALTY_FACTOR = 0.1
    num_bucket_sizes = len(bucket_sizes)
    num_dists = len(dists)
    ii = np.indices((num_bucket_sizes, num_dists))
    d = ii[0]**2 + DIST_PENALTY_FACTOR * ii[1]**2
    for bucket_idx, dist_idx in zip(*divmod(np.argsort(d, axis=None), d.shape[1])):
        yield bucket_sizes[bucket_idx], dists[dist_idx]

################################################################################
