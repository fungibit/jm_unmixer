$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$   JOINMARKET UNMIXER   $$$$$$$$$$$$$$$$$$$$$$$$$$
$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$


==== ABOUT ====

This is a JoinMarket ("JM") transaction unmixing tool.  It includes scripts for finding JM
transactions ("jmtxs") on the blockchain, for analyzing the jmtxs found, and for inspecting
the "unmixed" txs.

A jmtx is unmixed by ruling out outputs from belonging to a taker.  In an N-party jmtx, if
the tool finds N-1 of the "mix" outputs to belong to makers, the tx is considered unmixed,
because we know (with high certainty) the last mix output belongs to the taker.
If the tool finds fewer than N-1 outputs to belong to makers (but >0), the tx is considered
partially unmixed. That is still meaningful, because the mixing was less effective than the
taker expected (and paid for), although it wasn't completely worthless.

==== CONTACT ====

Feel free to contact me at: fungibit@yandex.com
PGP fingerprint: A42F BB89 217E 4C20 F61C B88E 6A7D 2F9B C7BD E719
Bitcoin address for donations: 1J9xoksroyBQkVCoDZMUxBHympRpJVWmeB


==== DISCLAIMER ====

This is a prototype-quality proof-of-concept-level implementation.  It probably contains many
bugs.  Many modification and improvements can be added.

Feel free to clone it and/or submit pull requests.


==== REQUIREMENTS ====

In order to run the analysis, you would need:

* bitcoin rpc server, running with txindex=1
* python3
* numpy
* bitcoinrpc (pip install python-bitcoinrpc)
* click (pip install click) -- optional, for displaying nice progress bars


==== SETUP ====

get source:
 % git clone https://github.com/fungibit/jm_unmixer

set PYTHONPATH appropriately:
 % export PYTHONPATH=/path/to/jm_unmixer/
To test PYTHONPATH:
 % python3 -c 'import jm_unmixer; print("ok")'

Make sure BTCRPC_CONFIG_FILE variable is set correctly in btccommon.py.
 % python3 -c 'import os; from jm_unmixer.btccommon import BTCRPC_CONFIG_FILE as conf; print("%s: %s" % (conf, "ok" if os.path.exists(conf) else "DOES NOT EXIST"))'
If not, edit jm_unmixer/btccommon.py accordingly.


==== RUNNING IT ====

STEP 1: Collecting JMTXs

Run find_jmtxs.py script on all the blocks you want to scan.  E.g.:
 % python3 bin/find_jmtxs.py 360000 420000 -o data/jmtxs.pkl
Notes:
* There is no point scanning before block 360000 (no JMTXs)
* This step can take a very long time (a few days) to complete. Feel free to split it to chunks
  and/or play with the "-w" (num_workers) cli option.
* Instead of waiting this long, you may use the included txids.txt file (data/txids.txt), which
  includes jmtxids up to block 419999. Run:
 % python3 bin/find_jmtxs.py data/txids.txt -o data/jmtxs.pkl
* You can also use a hybrid approach: use data/txids.txt for blocks up to 419999, and run the
  "full" scan starting block 420000 (and use the two output files together in STEP 2)

STEP 2: Analyzing JMTXs

Run analyze_jmtxs.py on the jmtxs generated in the previous step:
 % python3 bin/analyze_jmtxs.py data/jmtxs.pkl -o data/tainted_jmtxs.pkl
Notes:
* This step can take an hour or more to complete
* You may pass multiple jmtxs files

STEP 3: Inspecting Unmixed JMTXs

Run print_unmixed_jmtx.py on the tainted jmtxs generated in the previous step:
 % python3 bin/print_unmixed_jmtx.py -i data/tainted_jmtxs.pkl
Notes:
* The script will automatically select the "most impressive" unmixed tx, but you can also choose
  another tx to inspect

