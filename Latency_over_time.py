import pandas as pd
import matplotlib.pyplot as plt
import os

# 1. Define the file path
file_path = '/home/merajpi/Nabil/logs/latency_analysis_0154-28042026.csv'
output_dir = os.path.dirname(file_path)

# 2. Load the data
try:
    df = pd.read_csv(file_path)
    
    # 3. Process the Timestamp to Time in Seconds
    # Convert string to datetime objects
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    # Calculate elapsed time in seconds from the first record
    df['Time_s'] = (df['Timestamp'] - df['Timestamp'].iloc[0]).dt.total_seconds()
    
    # 4. Set Global Plotting Parameters for Academic Use
    plt.rcParams.update({
        'font.family': 'serif',       # Professional serif font
        'font.size': 11,              # Standard paper font size
        'axes.labelsize': 12,
        'axes.titlesize': 13,
        'legend.fontsize': 10,
        'figure.facecolor': 'white',  # Pure white background
        'axes.facecolor': 'white',
        'grid.alpha': 0.3,
        'grid.linestyle': '--'
    })

    # --- GRAPH 1: Telemetry Gap vs. Time ---
    plt.figure(figsize=(8, 5))
    plt.plot(df['Time_s'], df['Telemetry_Gap_ms'], color='#1f77b4', linewidth=1, label='Telemetry Gap')
    
    plt.title('Telemetry Transmission Gap over Time', fontweight='bold')
    plt.xlabel('Time (seconds)')
    plt.ylabel('Latency (ms)')
    plt.grid(True)
    plt.legend(loc='upper right')
    
    # Save to the same directory
    telemetry_plot_path = os.path.join(output_dir, 'telemetry_gap_vs_time.png')
    plt.savefig(telemetry_plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved: {telemetry_plot_path}")

    # --- GRAPH 2: Blockchain TX Latency vs. Time ---
    plt.figure(figsize=(8, 5))
    plt.plot(df['Time_s'], df['Blockchain_TX_Latency_ms'], color='#d62728', linewidth=1, label='Blockchain TX')
    
    plt.title('Blockchain Transaction Latency over Time', fontweight='bold')
    plt.xlabel('Time (seconds)')
    plt.ylabel('Latency (ms)')
    plt.grid(True)
    plt.legend(loc='upper right')
    
    # Save to the same directory
    blockchain_plot_path = os.path.join(output_dir, 'blockchain_tx_latency_vs_time.png')
    plt.savefig(blockchain_plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved: {blockchain_plot_path}")

except FileNotFoundError:
    print(f"Error: The file at {file_path} was not found.")
except Exception as e:
    print(f"An error occurred: {e}")