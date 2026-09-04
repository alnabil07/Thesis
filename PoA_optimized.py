"""
================================================================================
  OPTIMIZED PoA — Blockchain-Induced Latency, Optimized Transaction Pipeline
  THESIS: Quantitative Analysis and Optimization of Blockchain-Induced
          Latency in Real-Time Embedded Flight Control Systems
  Chain  : Private Ethereum PoA (Clique, chainId=1337, 2s block time)
  Geth   : v1.13.15-stable  |  web3.py v6+

  OPTIMIZATIONS APPLIED (vs. the original PoA script):

    1. NON-BLOCKING TX PIPELINE
       Submission + receipt wait now run on a background thread (same
       pattern as the PoS script), so the MAVLink read loop / curses UI
       never stall on a blockchain call. This directly fixes the 488ms
       telemetry-gap spike found in the unoptimized script, which
       coincided exactly with a synchronous send_transaction() call.

    2. LOCAL (OFFLINE) TRANSACTION SIGNING
       The account's private key is decrypted from the keystore ONCE at
       startup and held in memory; every transaction is signed locally
       with eth_account and submitted via send_raw_transaction(). The
       node no longer needs to unlock or hold the key at all, so
       --unlock / --allow-insecure-unlock / --rpc.enabledeprecatedpersonal
       can be dropped from the Geth command entirely. This also removes
       the node-side decrypt+sign step from the critical path of every
       single transaction, and closes the insecure-unlock RPC exposure.

    3. CACHED, PERIODICALLY-REFRESHED GAS PRICE
       Avoids an RPC round trip (w3.eth.gas_price) on every transaction.

    4. LOCALLY-TRACKED NONCE
       Fetched once at startup, incremented in memory. Avoids an RPC
       round trip per transaction; safe without locking because only the
       worker thread ever touches it.

    5. BLOCK NUMBER FROM THE RECEIPT
       Read blockNumber off the receipt instead of issuing a separate
       w3.eth.block_number call — removes another per-tx RPC round trip.

    6. PERSISTENT, BUFFERED CSV FILE HANDLE
       Opened once for the whole session instead of being opened,
       written, and closed on every single MAVLink message (a filesystem
       syscall at ~300 Hz in the original script).

    7. O(1) RUNNING MEAN/STD (Welford-style sliding sum/sum-of-squares)
       for the telemetry-gap statistics, instead of recomputing
       statistics.mean()/stdev() over the full rolling window on every
       single message.

    8. TUNED HTTP CONNECTION POOLING
       A shared requests.Session with an explicit connection pool, so
       every JSON-RPC call reuses a warm TCP connection.

  NOTE ON COMPARABILITY: this script now waits for the transaction
  receipt, so Blockchain_TX_Latency_ms here means the same thing as the
  PoS script's T_total (confirmed latency), not just submission time as
  in the original PoA script. Treat this as a corrected/optimized PoA
  case rather than a drop-in replacement for old PoA CSVs when comparing.
================================================================================
"""

import time
import curses
import csv
import os
import sys
import json
import getpass
import threading
import queue
import copy
import subprocess
import statistics
from datetime import datetime
from collections import deque

import requests
from pymavlink import mavutil
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

# ============================================================
#  CONFIGURATION — edit only this section if needed
# ============================================================
DEVICE           = '/dev/ttyAMA0'   # MAVLink serial port
BAUD             = 921600           # Serial baud rate
DISPLAY_INTERVAL = 0.1              # Terminal refresh rate (seconds)
TX_INTERVAL      = 2.0              # Blockchain TX interval (seconds)

RPC_URL          = 'http://127.0.0.1:8545'
CHAIN_ID         = 1337
MY_ADDRESS       = Web3.to_checksum_address("0x11Db73254c357F47B1194616B0142f738d0f3124")

# TODO: point this at your PoA account's actual keystore file.
KEYSTORE_PATH    = "/home/merajpi/Nabil/geth-poa-data/keystore/UTC--<your-poa-keystore-file>"
# Never hardcode the password in source. Set this env var before running,
# e.g.  export POA_KEYSTORE_PASSWORD='...'
# If it's not set, you'll be prompted securely (no echo) at startup.
KEYSTORE_PASSWORD_ENV = "POA_KEYSTORE_PASSWORD"

LOG_DIR          = "/home/merajpi/Nabil/logs"
WINDOW_SIZE      = 50                # Rolling stats window (messages)

GAS_PRICE_REFRESH_INTERVAL = 30.0    # seconds; re-fetch gas price this often, not every tx
CSV_FLUSH_EVERY  = 1                 # flush to disk every N rows (1 = safest, still avoids reopen/close)

# ============================================================
#  SETUP — pooled HTTP session + PoA middleware
# ============================================================
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=10, max_retries=0)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

w3 = Web3(Web3.HTTPProvider(RPC_URL, session=_session, request_kwargs={"timeout": 30}))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
log_filename  = os.path.join(LOG_DIR, f"latency_analysis_opt_{timestamp_str}.csv")

CSV_HEADER = [
    "Timestamp",
    "Telemetry_Gap_ms",
    "Telemetry_Mean_Gap_ms",
    "Telemetry_Max_Gap_ms",
    "Telemetry_Std_Gap_ms",
    "Blockchain_TX_Latency_ms",   # NOTE: now confirmed T_total, see header docstring
    "TX_Count",
    "Block_Number",
    "Blockchain_Status",
    "Altitude_m",
    "Speed_mps",
    "Heading_deg",
    "Latitude",
    "Longitude",
    "Voltage_V",
    "Current_A",
    "Satellites",
]


# ============================================================
#  OPTIMIZATION 7 — O(1) running mean/std over a sliding window
# ============================================================
class RunningStats:
    """Sliding-window mean/std in O(1) per update instead of recomputing
    statistics.mean()/stdev() over the whole window every message."""

    def __init__(self, maxlen):
        self.values = deque(maxlen=maxlen)
        self._sum = 0.0
        self._sumsq = 0.0

    def add(self, x):
        if len(self.values) == self.values.maxlen:
            old = self.values[0]
            self._sum -= old
            self._sumsq -= old * old
        self.values.append(x)
        self._sum += x
        self._sumsq += x * x

    @property
    def mean(self):
        n = len(self.values)
        return self._sum / n if n else 0.0

    @property
    def std(self):
        n = len(self.values)
        if n < 2:
            return 0.0
        mean = self.mean
        var = max(self._sumsq / n - mean * mean, 0.0)  # guard tiny float negatives
        return var ** 0.5

    @property
    def max(self):
        return max(self.values) if self.values else 0.0

    def __len__(self):
        return len(self.values)


gap_stats = RunningStats(WINDOW_SIZE)

# ============================================================
#  SHARED BLOCKCHAIN STATE (written by worker thread, read by UI)
# ============================================================
tx_queue = queue.Queue()
stats_lock = threading.Lock()
blockchain_stats = {
    "latency_ms": 0.0,
    "status": "WAITING FOR FIRST TX...",
    "tx_count": 0,
    "current_block": 0,
}


# ============================================================
#  OPTIMIZATION 2 — load & decrypt the signing key ONCE at startup
# ============================================================
def load_private_key():
    password = os.environ.get(KEYSTORE_PASSWORD_ENV)
    if not password:
        password = getpass.getpass(f"Keystore password for {MY_ADDRESS}: ")
    with open(KEYSTORE_PATH, "r") as f:
        keystore_json = f.read()
    private_key = Account.decrypt(keystore_json, password)
    acct = Account.from_key(private_key)
    if acct.address.lower() != MY_ADDRESS.lower():
        raise RuntimeError(
            f"Keystore address {acct.address} does not match configured "
            f"MY_ADDRESS {MY_ADDRESS} — check KEYSTORE_PATH."
        )
    return private_key


def get_raw_transaction_bytes(signed_txn):
    """eth-account renamed this attribute across versions; support both."""
    raw = getattr(signed_txn, "raw_transaction", None)
    if raw is None:
        raw = signed_txn.rawTransaction
    return raw


# ============================================================
#  HELPERS
# ============================================================
def safe_addstr(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()
    if y >= h or x >= w:
        return
    text = str(text)
    if x + len(text) > w:
        text = text[:w - x - 1]
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def check_blockchain():
    try:
        if not w3.is_connected():
            return False, "HTTPProvider not connected"
        block = w3.eth.block_number
        chain = w3.eth.chain_id
        if chain != CHAIN_ID:
            return False, f"chainId mismatch: got {chain}, expected {CHAIN_ID}"
        return True, block
    except Exception as e:
        return False, str(e)[:60]


# ============================================================
#  OPTIMIZATION 1, 3, 4, 5 — background worker: local signing,
#  cached nonce, cached gas price, receipt-derived block number
# ============================================================
def blockchain_worker(private_key):
    nonce = w3.eth.get_transaction_count(MY_ADDRESS, "pending")
    cached_gas_price = max(w3.eth.gas_price, w3.to_wei(1, "gwei"))
    last_gas_refresh = time.perf_counter()

    while True:
        telemetry_snapshot = tx_queue.get()
        tx_start = time.perf_counter()

        try:
            payload = (
                f"ALT:{telemetry_snapshot['altitude']:.2f},"
                f"SPD:{telemetry_snapshot['speed']:.2f},"
                f"LAT:{telemetry_snapshot['latitude']:.6f},"
                f"LON:{telemetry_snapshot['longitude']:.6f},"
                f"HDG:{telemetry_snapshot['heading']},"
                f"SAT:{telemetry_snapshot['satellites']}"
            )

            now = time.perf_counter()
            if now - last_gas_refresh >= GAS_PRICE_REFRESH_INTERVAL:
                cached_gas_price = max(w3.eth.gas_price, w3.to_wei(1, "gwei"))
                last_gas_refresh = now

            tx = {
                "from": MY_ADDRESS,
                "to": MY_ADDRESS,
                "value": 0,
                "gas": 120_000,
                "gasPrice": cached_gas_price,
                "nonce": nonce,
                "data": w3.to_hex(text=payload),
                "chainId": CHAIN_ID,
            }

            signed = Account.sign_transaction(tx, private_key=private_key)
            tx_hash = w3.eth.send_raw_transaction(get_raw_transaction_bytes(signed))
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            t_total = (time.perf_counter() - tx_start) * 1000.0
            nonce += 1

            with stats_lock:
                blockchain_stats["latency_ms"] = t_total
                blockchain_stats["status"] = "OK"
                blockchain_stats["tx_count"] += 1
                blockchain_stats["current_block"] = receipt["blockNumber"]

        except Exception as e:
            err_msg = str(e)[:40]
            with stats_lock:
                blockchain_stats["latency_ms"] = -1.0
                blockchain_stats["status"] = f"ERR: {err_msg}"

            if "nonce" in err_msg.lower() or "underpriced" in err_msg.lower():
                try:
                    nonce = w3.eth.get_transaction_count(MY_ADDRESS, "pending")
                except Exception:
                    pass

        tx_queue.task_done()


# ============================================================
#  MAIN CURSES LOOP
# ============================================================
def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN,  -1)
    curses.init_pair(2, curses.COLOR_RED,    -1)
    curses.init_pair(3, curses.COLOR_CYAN,   -1)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)

    BOLD  = curses.A_BOLD
    REV   = curses.A_REVERSE
    GREEN = curses.color_pair(1)
    RED   = curses.color_pair(2)
    CYAN  = curses.color_pair(3)

    # ── Startup: verify blockchain ────────────────────────────
    stdscr.erase()
    safe_addstr(stdscr, 0, 0,
        "=== THESIS: BLOCKCHAIN LATENCY IN EMBEDDED FLIGHT CONTROL (PoA, OPT) ===", REV)
    safe_addstr(stdscr, 2, 0, "Checking blockchain node...", BOLD)
    stdscr.refresh()

    ok, info = check_blockchain()
    if ok:
        safe_addstr(stdscr, 3, 0,
            f"  Blockchain OK — chainId={CHAIN_ID}  current block=#{info}",
            GREEN | BOLD)
    else:
        safe_addstr(stdscr, 3, 0,
            f"  Blockchain UNREACHABLE: {info}", RED | BOLD)
        safe_addstr(stdscr, 5, 0,
            "  Start Geth first, then re-run.  Press any key to exit.")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    # Load signing key BEFORE starting curses-dependent prompts would be
    # awkward, so this happens outside curses in __main__ instead — see
    # bottom of file. By this point PRIVATE_KEY is already available.
    worker_thread = threading.Thread(target=blockchain_worker, args=(PRIVATE_KEY,), daemon=True)
    worker_thread.start()

    # ── Startup: MAVLink ──────────────────────────────────────
    safe_addstr(stdscr, 5, 0,
        f"  Connecting MAVLink: {DEVICE} @ {BAUD} baud ...", BOLD)
    stdscr.refresh()

    port_check = subprocess.run(["fuser", DEVICE], capture_output=True, text=True)
    if port_check.stdout.strip():
        pids = port_check.stdout.strip()
        safe_addstr(stdscr, 6, 0,
            f"  MAVLink FAILED: {DEVICE} is already held by PID {pids}", RED | BOLD)
        safe_addstr(stdscr, 7, 0,
            f"  Run: kill {pids}   then restart this script.", RED)
        safe_addstr(stdscr, 9, 0, "  Press any key to exit.")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    try:
        connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
        connection.wait_heartbeat(timeout=10)
    except Exception as e:
        safe_addstr(stdscr, 6, 0, f"  MAVLink FAILED: {e}", RED | BOLD)
        safe_addstr(stdscr, 8, 0, "  Press any key to exit.")
        stdscr.nodelay(False)
        stdscr.getch()
        return

    connection.mav.request_data_stream_send(
        connection.target_system,
        connection.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,
        20, 1
    )

    # ── OPTIMIZATION 6: open the CSV ONCE for the whole session ─
    csv_file = open(log_filename, mode="w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(CSV_HEADER)
    csv_file.flush()
    rows_since_flush = 0

    # ── State variables ───────────────────────────────────────
    last_msg_time     = time.perf_counter()
    last_display_time = time.perf_counter()
    last_tx_time      = time.perf_counter() - TX_INTERVAL

    gap = 0.0
    height_offset = None

    telemetry = {
        'latitude': 0.0, 'longitude': 0.0,
        'altitude': 0.0, 'pos_z':     0.0,
        'voltage':  0.0, 'current':   0.0,
        'speed':    0.0, 'heading':   0,
        'satellites': 0,
    }

    try:
        # ============================================================
        #  MAIN LOOP
        # ============================================================
        while True:
            key = stdscr.getch()
            if key == ord('q'):
                break
            if key == ord('r'):
                height_offset = None

            try:
                msg = connection.recv_match(blocking=False)
            except Exception as serial_err:
                safe_addstr(stdscr, 20, 0,
                    f"  !! SERIAL DISCONNECTED: {str(serial_err)[:60]}",
                    RED | BOLD)
                stdscr.refresh()
                time.sleep(2)
                break

            if msg:
                now = time.perf_counter()

                gap = (now - last_msg_time) * 1000.0
                gap_stats.add(gap)          # OPTIMIZATION 7: O(1) update
                last_msg_time = now

                m = msg.get_type()
                if m == 'GLOBAL_POSITION_INT':
                    telemetry['latitude']  = msg.lat / 1e7
                    telemetry['longitude'] = msg.lon / 1e7
                elif m == 'LOCAL_POSITION_NED':
                    telemetry['pos_z'] = msg.z
                elif m == 'SYS_STATUS':
                    telemetry['voltage'] = msg.voltage_battery / 1000.0
                    telemetry['current'] = msg.current_battery / 100.0
                elif m == 'VFR_HUD':
                    telemetry['speed']   = msg.groundspeed
                    telemetry['heading'] = msg.heading
                elif m == 'GPS_RAW_INT':
                    telemetry['satellites'] = msg.satellites_visible

                raw_h = -telemetry['pos_z']
                if height_offset is None:
                    height_offset = raw_h
                telemetry['altitude'] = raw_h - height_offset

                # ── Hand off to background thread (non-blocking) ───
                if now - last_tx_time >= TX_INTERVAL:
                    last_tx_time = now
                    tx_queue.put(copy.deepcopy(telemetry))

                # ── Read latest blockchain stats & log ─────────────
                with stats_lock:
                    bc_latency = blockchain_stats["latency_ms"]
                    bc_status  = blockchain_stats["status"]
                    bc_txcount = blockchain_stats["tx_count"]
                    bc_block   = blockchain_stats["current_block"]

                csv_writer.writerow([
                    datetime.now().isoformat(),
                    f"{gap:.3f}",
                    f"{gap_stats.mean:.3f}",
                    f"{gap_stats.max:.3f}",
                    f"{gap_stats.std:.3f}",
                    f"{bc_latency:.3f}",
                    bc_txcount,
                    bc_block,
                    bc_status,
                    f"{telemetry['altitude']:.3f}",
                    f"{telemetry['speed']:.3f}",
                    telemetry['heading'],
                    f"{telemetry['latitude']:.7f}",
                    f"{telemetry['longitude']:.7f}",
                    f"{telemetry['voltage']:.3f}",
                    f"{telemetry['current']:.3f}",
                    telemetry['satellites'],
                ])
                rows_since_flush += 1
                if rows_since_flush >= CSV_FLUSH_EVERY:
                    csv_file.flush()
                    rows_since_flush = 0

            # ── Display ───────────────────────────────────────────
            if time.perf_counter() - last_display_time >= DISPLAY_INTERVAL:
                with stats_lock:
                    bc_latency = blockchain_stats["latency_ms"]
                    bc_status  = blockchain_stats["status"]
                    bc_txcount = blockchain_stats["tx_count"]
                    bc_block   = blockchain_stats["current_block"]

                stdscr.erase()

                safe_addstr(stdscr, 0, 0,
                    "=== BLOCKCHAIN LATENCY IN EMBEDDED FLIGHT CONTROL SYSTEM (PoA, OPT) ===",
                    REV)

                safe_addstr(stdscr, 2, 0,
                    f"Log: {os.path.basename(log_filename)}"
                    f"   Block: #{bc_block}"
                    f"   TX count: {bc_txcount}", CYAN)

                safe_addstr(stdscr, 4, 0, "TELEMETRY LINK QUALITY", BOLD)
                safe_addstr(stdscr, 5, 2, f"Current gap : {gap:8.3f} ms")
                safe_addstr(stdscr, 6, 2,
                    f"Mean gap    : {gap_stats.mean:8.3f} ms"
                    f"  (window={len(gap_stats)})")
                safe_addstr(stdscr, 7, 2, f"Max gap     : {gap_stats.max:8.3f} ms")
                safe_addstr(stdscr, 8, 2, f"Std dev     : {gap_stats.std:8.3f} ms")

                safe_addstr(stdscr, 10, 0, "BLOCKCHAIN (PoA, optimized pipeline)", BOLD)
                bc_color = GREEN if bc_status == "OK" else RED
                safe_addstr(stdscr, 11, 2, "T_total     : ")
                safe_addstr(stdscr, 11, 16,
                    f"{bc_latency:8.3f} ms" if bc_latency >= 0 else "      FAILED",
                    bc_color | BOLD)
                safe_addstr(stdscr, 12, 2, f"Status      : {bc_status}", bc_color)
                safe_addstr(stdscr, 13, 2,
                    "(signed locally, sent async; UI never blocks on it)", CYAN)

                safe_addstr(stdscr, 15, 0, "FLIGHT DATA", BOLD)
                safe_addstr(stdscr, 16, 2,
                    f"Altitude : {telemetry['altitude']:7.2f} m"
                    f"   Speed : {telemetry['speed']:5.2f} m/s"
                    f"   Heading : {telemetry['heading']:3d} deg")
                safe_addstr(stdscr, 17, 2,
                    f"GPS      : {telemetry['latitude']:11.7f},"
                    f" {telemetry['longitude']:12.7f}"
                    f"   Sats: {telemetry['satellites']}")
                safe_addstr(stdscr, 18, 2,
                    f"Battery  : {telemetry['voltage']:.2f} V"
                    f"  /  {telemetry['current']:.2f} A")

                safe_addstr(stdscr, 20, 0,
                    "[q] quit   [r] reset altitude baseline", CYAN)

                stdscr.refresh()
                last_display_time = time.perf_counter()

    finally:
        csv_file.flush()
        csv_file.close()

    curses.endwin()
    print(f"\nSession complete.")
    print(f"CSV log : {log_filename}")
    with stats_lock:
        print(f"Total TX confirmed: {blockchain_stats['tx_count']}")


# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        # Decrypt the key BEFORE entering curses, so getpass() (if needed)
        # behaves normally instead of fighting curses for the terminal.
        PRIVATE_KEY = load_private_key()
        print("Key loaded, starting...")
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        try:
            curses.endwin()
        except Exception:
            pass
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        sys.exit(1)
