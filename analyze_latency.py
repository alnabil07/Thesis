import pandas as pd
import glob
import os

def analyze_results():
    print("\n" + "="*60)
    print("      BLOCKCHAIN LATENCY FINAL QUANTITATIVE ANALYSIS")
    print("="*60 + "\n")

    log_dir = 'thesis_logs'
    
    # 1. Baseline File
    baseline_path = os.path.join(log_dir, 'baseline.csv')
    
    # 2. Get newest Idle log (from our previous phase)
    idle_logs = glob.glob(os.path.join(log_dir, 'latency_log_*.csv'))
    idle_path = max(idle_logs, key=os.path.getctime) if idle_logs else None
    
    # 3. Get newest Active TX log (the one you just ran!)
    tx_logs = glob.glob(os.path.join(log_dir, 'latency_tx_*.csv'))
    tx_path = max(tx_logs, key=os.path.getctime) if tx_logs else None

    files_to_process = [
        ("BASELINE", baseline_path), 
        ("PoA IDLE", idle_path), 
        ("PoA ACTIVE (TX)", tx_path)
    ]

    results = []

    for label, path in files_to_process:
        if not path or not os.path.exists(path):
            print(f"[SKIP] {label} file not found.")
            continue
            
        df = pd.read_csv(path)
        
        # Filter out noise (first 50 samples)
        df = df.iloc[50:] 

        metrics = {
            "Mode": label,
            "Avg Gap (ms)": df['Update_Gap_ms'].mean(),
            "Max Gap (ms)": df['Update_Gap_ms'].max(),
            "Jitter (StdDev)": df['Update_Gap_ms'].std(),
            "Samples": len(df)
        }
        results.append(metrics)

    # Display Table
    summary_df = pd.DataFrame(results)
    print(summary_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    
    # Comparison Logic
    if len(results) >= 3:
        total_overhead = ((results[2]['Avg Gap (ms)'] - results[0]['Avg Gap (ms)']) / results[0]['Avg Gap (ms)']) * 100
        print(f"\n[CONCLUSION] Total Blockchain Traffic overhead: {total_overhead:.2f}%")
        
        jitter_impact = results[2]['Jitter (StdDev)'] - results[0]['Jitter (StdDev)']
        print(f"[CONCLUSION] Flight Control Jitter increased by {jitter_impact:.4f}ms under load.")

if __name__ == "__main__":
    analyze_results()