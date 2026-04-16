import time
import curses
import csv
import os
from pymavlink import mavutil
from web3 import Web3
# New naming for Web3 v7
from web3.middleware import ExtraDataToPOAMiddleware 

# --- Configuration ---
DEVICE = '/dev/ttyAMA0'
BAUD = 921600
DISPLAY_INTERVAL = 0.1  
BLOCKCHAIN_MODE = "ON_TX"
TX_INTERVAL = 2.0  

# --- Blockchain Setup ---
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
# Using the new Middleware name
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0) 
my_address = "0x65e24BBF350cC4665309513d423eA4f6F1CC49f7"

if not os.path.exists('thesis_logs'):
    os.makedirs('thesis_logs')
log_filename = f"thesis_logs/latency_tx_{int(time.time())}.csv"

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(1) 

    stdscr.addstr(1, 0, f"Connecting to {DEVICE}...", curses.A_BOLD)
    stdscr.refresh()
    
    connection = mavutil.mavlink_connection(DEVICE, baud=BAUD)
    connection.wait_heartbeat()
    
    connection.mav.request_data_stream_send(
        connection.target_system, connection.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)

    with open(log_filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Update_Gap_ms", "Blockchain_Status"])

    last_msg_time = time.time()
    last_display_update = time.time()
    last_tx_time = time.time()
    latency = 0.0
    tx_count = 0
    error_msg = "Blockchain: Ready"
    
    data = {'volt': 0.0, 'alt': 0.0}

    while True:
        key = stdscr.getch()
        if key == ord('q'):
            break

        msg = connection.recv_match(blocking=False)
        if msg:
            m_type = msg.get_type()
            current_time = time.time()
            latency = (current_time - last_msg_time) * 1000
            last_msg_time = current_time

            with open(log_filename, mode='a', newline='') as f:
                csv.writer(f).writerow([current_time, latency, BLOCKCHAIN_MODE])

            if m_type == 'VFR_HUD':
                data['alt'] = msg.alt
            elif m_type == 'SYS_STATUS':
                data['volt'] = msg.voltage_battery / 1000.0

            # 2. SEND TO BLOCKCHAIN
            if current_time - last_tx_time > TX_INTERVAL:
                try:
                    tx = {
                        'from': my_address,
                        'to': my_address,
                        'value': 0,
                        'gas': 30000,
                        'gasPrice': w3.eth.gas_price,
                        'nonce': w3.eth.get_transaction_count(my_address),
                        'data': w3.to_hex(text=f"Alt:{data['alt']}"),
                    }
                    w3.eth.send_transaction(tx)
                    tx_count += 1
                    error_msg = "Blockchain: TX Sent Successfully!"
                except Exception as e:
                    error_msg = f"BC Error: {str(e)[:40]}"
                
                last_tx_time = current_time

        if time.time() - last_display_update > DISPLAY_INTERVAL:
            stdscr.erase()
            stdscr.addstr(0, 0, "=== MAVLink + BLOCKCHAIN ACTIVE LOGGING ===", curses.A_REVERSE)
            stdscr.addstr(2, 0, f"Mode: {BLOCKCHAIN_MODE} | TX Sent: {tx_count}", curses.A_BOLD)
            stdscr.addstr(5, 0, f"Link Gap: {latency:.2f}ms")
            stdscr.addstr(6, 0, f"Battery:  {data['volt']:.2f}V")
            stdscr.addstr(9, 0, f"Status: {error_msg}")
            stdscr.addstr(11, 0, "Press [q] to stop")
            stdscr.refresh()
            last_display_update = time.time()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"\n[ERROR] {e}")