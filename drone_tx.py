import time, curses, csv, os, sys, statistics
from datetime import datetime
from collections import deque
from pymavlink import mavutil
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# --- CONFIG ---
DEVICE = '/dev/ttyAMA0' 
BAUD = 921600
RPC_URL = 'http://127.0.0.1:8545' # Pi talks to itself locally
MY_ADDRESS = "0x11Db73254c357F47B1194616B0142f738d0f3124"

w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

def main(stdscr):
    # (Existing curses setup and MAVLink connection logic from previous script)
    # Ensure nonce_cache = None at start
    nonce_cache = None
    tx_count = 0

    while True:
        # ... [Logic to get MAVLink msg] ...
        
        # SEND TO BLOCKCHAIN
        if time.perf_counter() - last_tx_time >= 2.0:
            tx_start = time.perf_counter()
            try:
                if nonce_cache is None:
                    nonce_cache = w3.eth.get_transaction_count(MY_ADDRESS, 'pending')
                
                payload = f"ALT:{alt:.2f},LAT:{lat:.6f},LON:{lon:.6f}"
                tx = {
                    'from': MY_ADDRESS, 'to': MY_ADDRESS, 'value': 0,
                    'gas': 100000, 'gasPrice': w3.eth.gas_price,
                    'nonce': nonce_cache, 'data': w3.to_hex(text=payload), 'chainId': 1337
                }
                w3.eth.send_transaction(tx)
                nonce_cache += 1
                tx_count += 1
            except Exception as e:
                nonce_cache = None # Reset on error