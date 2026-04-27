"""
================================================================================
  THESIS: Quantitative Analysis and Optimization of Blockchain-Induced
          Latency in Real-Time Embedded Flight Control Systems
  Chain  : Private Ethereum PoS (Proof of Stake)
================================================================================
"""

import time
import curses
import csv
import os
import sys
import threading
import queue
import copy
import statistics
from datetime import datetime
from collections import deque

from pymavlink import mavutil
from web3 import Web3

# ============================================================
#  CONFIGURATION
# ============================================================
DEVICE           = '/dev/ttyAMA0'
BAUD             = 921600
DISPLAY_INTERVAL = 0.1
TX_INTERVAL      = 15.0  # Increased for PoS Slot times (12s)

RPC_URL          = 'http://127.0.0.1:8545'
CHAIN_ID         = 1337
MY_ADDRESS       = "0x55fa363e65c1cd9172F8D1E34FFD4A35A52f3998"

LOG_DIR          = "/home/merajpi/Nabil/logs"
WINDOW_SIZE      = 50

# ============================================================
#  SETUP (PoS VERSION - No Middleware)
# ============================================================
w3 = Web3(Web3.HTTPProvider(RPC_URL))
# Note: ExtraDataToPOAMiddleware removed for PoS compatibility

tx_queue = queue.Queue()
blockchain_stats = {
    "latency_ms": 0.0,
    "status": "INITIALIZING...",
    "tx_count": 0,
    "current_block": 0
}

os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
log_filename  = os.path.join(LOG_DIR, f"latency_pos_{timestamp_str}.csv")

CSV_HEADER = [
    "Timestamp", "Telemetry_Gap_ms", "Telemetry_Mean_Gap_ms", "Telemetry_Max_Gap_ms",
    "Telemetry_Std_Gap_ms", "Blockchain_T_total_ms", "TX_Count", "Block_Number",
    "Blockchain_Status", "Altitude_m", "Speed_mps", "Heading_deg",
    "Latitude", "Longitude", "Voltage_V", "Current_A", "Satellites"
]

# ============================================================
#  WORKER & HELPERS
# ============================================================
def append_csv(row: list):
    with open(log_filename, mode='a', newline='') as f:
        csv.writer(f).writerow(row)

def blockchain_worker():
    """Background thread to measure T_total in PoS environment"""
    try:
        nonce = w3.eth.get_transaction_count(MY_ADDRESS, 'pending')
    except:
        nonce = 0

    while True:
        telemetry_snapshot, gap_stats = tx_queue.get()
        t_start = time.perf_counter()
        
        try:
            payload = (
                f"ALT:{telemetry_snapshot['altitude']:.2f},"
                f"SPD:{telemetry_snapshot['speed']:.2f},"
                f"LAT:{telemetry_snapshot['latitude']:.6f},"
                f"LON:{telemetry_snapshot['longitude']:.6f}"
            )

            tx = {
                'from': MY_ADDRESS, 'to': MY_ADDRESS, 'value': 0,
                'gas': 120_000, 
                'maxFeePerGas': w3.to_wei(2, 'gwei'), # PoS uses EIP-1559 fees
                'maxPriorityFeePerGas': w3.to_wei(1, 'gwei'),
                'nonce': nonce, 'data': w3.to_hex(text=payload), 'chainId': CHAIN_ID
            }

            tx_hash = w3.eth.send_transaction(tx)
            # wait_for_transaction_receipt will now block for ~12-24 seconds
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            t_total = (time.perf_counter() - t_start) * 1000.0
            
            blockchain_stats.update({
                "latency_ms": t_total, "status": "OK",
                "tx_count": blockchain_stats["tx_count"] + 1,
                "current_block": receipt['blockNumber']
            })

            append_csv([
                datetime.now().isoformat(), gap_stats['gap'], gap_stats['mean'],
                gap_stats['max'], gap_stats['std'], f"{t_total:.3f}",
                blockchain_stats["tx_count"], receipt['blockNumber'], "OK",
                f"{telemetry_snapshot['altitude']:.3f}", f"{telemetry_snapshot['speed']:.3f}",
                telemetry_snapshot['heading'], f"{telemetry_snapshot['latitude']:.7f}",
                f"{telemetry_snapshot['longitude']:.7f}", f"{telemetry_snapshot['voltage']:.3f}",
                f"{telemetry_snapshot['current']:.3f}", telemetry_snapshot['satellites']
            ])
            nonce += 1
        except Exception as e:
            blockchain_stats["status"] = f"ERR: {str(e)[:30]}"
            blockchain_stats["latency_ms"] = -1.0
            nonce = w3.eth.get_transaction_count(MY_ADDRESS, 'pending')
        
        tx_queue.task_done()

def safe_addstr(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()
    if y < h and x < w:
        try: stdscr.addstr(y, x, str(text)[:w-x-1], attr)
        except: pass

# ============================================================
#  MAIN
# ============================================================
def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_CYAN, -1)

    with open(log_filename, mode='w', newline='') as f:
        csv.writer(f).writerow(CSV_HEADER)

    connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
    connection.wait_heartbeat()

    worker_thread = threading.Thread(target=blockchain_worker, daemon=True)
    worker_thread.start()

    telemetry_gaps = deque(maxlen=WINDOW_SIZE)
    last_msg_time = last_display_time = time.perf_counter()
    last_tx_time = time.perf_counter() - TX_INTERVAL
    
    telemetry = {
        'latitude': 0.0, 'longitude': 0.0, 'altitude': 0.0, 
        'voltage': 0.0, 'current': 0.0, 'speed': 0.0, 'heading': 0, 'satellites': 0
    }

    while True:
        if stdscr.getch() == ord('q'): break
        
        msg = connection.recv_match(blocking=False)
        if msg:
            now = time.perf_counter()
            gap = (now - last_msg_time) * 1000.0
            telemetry_gaps.append(gap)
            last_msg_time = now

            # Handoff to Background Thread
            if now - last_tx_time >= TX_INTERVAL:
                last_tx_time = now
                gaps = list(telemetry_gaps)
                stats_snapshot = {
                    'gap': f"{gap:.2f}", 
                    'mean': f"{statistics.mean(gaps):.2f}",
                    'max': f"{max(gaps):.2f}",
                    'std': f"{statistics.stdev(gaps) if len(gaps)>1 else 0:.2f}"
                }
                tx_queue.put((copy.deepcopy(telemetry), stats_snapshot))

        if time.perf_counter() - last_display_time >= DISPLAY_INTERVAL:
            stdscr.erase()
            safe_addstr(stdscr, 0, 0, "=== PoS BLOCKCHAIN LATENCY ANALYSIS ===", curses.A_REVERSE)
            safe_addstr(stdscr, 2, 0, f"MAVLink Gap: {telemetry_gaps[-1] if telemetry_gaps else 0:.2f} ms", curses.color_pair(3))
            
            bc_col = curses.color_pair(1) if blockchain_stats["status"] == "OK" else curses.color_pair(2)
            safe_addstr(stdscr, 5, 2, f"PoS T_total Latency: {blockchain_stats['latency_ms']:.2f} ms", bc_col | curses.A_BOLD)
            safe_addstr(stdscr, 6, 2, f"Confirmed Block    : #{blockchain_stats['current_block']}")
            safe_addstr(stdscr, 7, 2, f"Status             : {blockchain_stats['status']}", bc_col)
            stdscr.refresh()
            last_display_time = time.perf_counter()

if __name__ == "__main__":
    curses.wrapper(main)