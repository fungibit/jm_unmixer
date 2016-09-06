"""
Basic tools for working with BTC blockchain/blocks/transactions.
"""

import os
import json
import decimal
from datetime import datetime

from http.client import CannotSendRequest, ResponseNotReady, BadStatusLine
from bitcoinrpc.authproxy import AuthServiceProxy

################################################################################
# Constants

BTCRPC_CONFIG_FILE = os.path.expanduser('~/.bitcoin/bitcoin.conf')
APPROX_BLOCK_DELTA_SECONDS = 60*10

################################################################################
# Communication related

_conn = None

def connection():
    global _conn
    if _conn is None:
        reconnect()
    return _conn

def reconnect():
    global _conn
    config = read_btcrpc_config()
    _conn = AuthServiceProxy('http://%s:%s@127.0.0.1:8332' % (config['rpcuser'], config['rpcpassword']))

def disconnect():
    global _conn
    _conn = None

def autoreconnect(func):
    def f(*a, **kw):
        try:
            return func(*a, **kw)
        except (CannotSendRequest, ResponseNotReady, BadStatusLine):
            reconnect()
            return func(*a, **kw)
    return f

def read_btcrpc_config():
    d = {}
    with open(BTCRPC_CONFIG_FILE) as F:
        for line in F:
            key, _, value = line.strip().partition('=')
            d[key] = value
    return d

@autoreconnect
def run_command(cmd, *args):
    func = getattr(connection(), cmd)
    return func(*args)

################################################################################
# BlockChain

class BlockChain(object):
    
    def __init__(self):
        pass

    #===================================================================================================================
    # blocks
    #===================================================================================================================
    
    def get_block_by_height(self, height):
        bid = run_command('getblockhash', height)
        return self.get_block_by_id(bid)
    
    def get_block_by_id(self, bid):
        return run_command('getblock', bid)

    def get_num_blocks(self):
        return run_command('getblockcount')

    def iter_blocks_by_heights(self, heights):
        for h in heights:
            yield self.get_block_by_height(h)

    def iter_blocks_by_ids(self, from_bid, to_bid):
        # to_bid can be None, meaning until the end
        bid = from_bid
        while True:
            block = self.get_block_by_id(bid)
            yield block
            if to_bid is not None and to_bid == bid:
                break
            bid = block['nextblockhash']
            
################################################################################

# Global singleton:
BLOCKCHAIN = BlockChain()
    
################################################################################
# Block

class Block(object):
    
    def __init__(self, json):
        self.json = json
    
    @property
    def id(self):
        return self.json['hash']
    
    @property
    def time(self):
        return datetime.utcfromtimestamp(self.json['time'])

    @property
    def height(self):
        return self.json['height']

    @property
    def num_txs(self):
        return len(self.txids)

    @property
    def txids(self):
        return self.json['tx']
    
    @property
    def txs(self):
        return list(self.iter_txs())
    
    def iter_txs(self):
        for txid in self.txids:
            yield Tx.from_id(txid)
    
    def __repr__(self):
        return '<%s #%s %s (%s)>' % (
            type(self).__name__,
            self.height,
            self.id,
            self.time,
        )

################################################################################
# Tx

class Tx(object):
    
    def __init__(self, json):
        self.json = json
    
    @classmethod
    def from_id(cls, txid):
        return cls(run_command(
            'getrawtransaction',
            txid,
            1,  # verbose=True, i.e. json formatted
        ))
    
    #===================================================================================================================
    # properties
    #===================================================================================================================
    
    @property
    def id(self):
        return self.json['txid']
    @property
    def size(self):
        return self.json['size']
    @property
    def time(self):
        return datetime.utcfromtimestamp(self.json['time'])
    @property
    def blocktime(self):
        return datetime.utcfromtimestamp(self.json['blocktime'])
    @property
    def blockhash(self):
        return self.json['blockhash']
    @property
    def num_confirmations(self):
        return self.json['confirmations']

    @property
    def vin(self):
        return self.json['vin']
    @property
    def vout(self):
        return self.json['vout']

    #===================================================================================================================
    # inputs / outputs
    #===================================================================================================================

    @property
    def vout_values(self):
        return [ vout['value'] for vout in self.vout ]

    @property
    def vin_values(self):
        return [
            self.get_vout_being_spent_by_vin(vin)['value']
            for vin in self.vin
        ]

    @property
    def total_vout_value(self):
        return sum(self.vout_values)
    
    @property
    def total_vin_value(self):
        return sum(self.vin_values)
    
    def get_vout_being_spent_by_vin(self, vin):
        tx = Tx.from_id(vin['txid'])
        vout = tx.vout[vin['vout']]
        return vout
    
    @property
    def fee(self):
        return self.total_vin_value - self.total_vout_value
   
    #===================================================================================================================
    # misc
    #===================================================================================================================

    def __repr__(self):
        return '<%s %s (%s)>' % ( type(self).__name__, self.id, self.time )
    
    def __str__(self):
        doc = dict(self.json)
        doc.pop('hex', None)
        return json.dumps(doc, indent = 2, cls = DecimalEncoder)

################################################################################
# misc

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)

################################################################################
# misc conveniences

import fileinput

def gen_txids_from_cli_args(args):
    if args and _is_hex(args[0]):
        # args are txids
        yield from args
    else:
        # args are files containing txids (or txids read from stdin)
        yield from fileinput.FileInput(args)

def _is_hex(x):
    try:
        int(x, 16)
        return True
    except ValueError:
        return False

################################################################################

