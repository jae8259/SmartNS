import os
import time
import subprocess
import argparse
from datetime import datetime

# === 配置区 ===
RDMA_DEV = "mlx5_0"
RDMA_PORT = "1"
NET_DEV = "enp28s0np0"

RDMA_METRICS = [
    # 1. 拥塞反馈闭环 (DCQCN 与流控状态)
    "np_ecn_marked_roce_packets",
    "np_cnp_sent",
    "rp_cnp_handled",
    "rp_cnp_ignored",

    # 2. 丢包、重传与序列号错误 (长尾延迟的核心元凶)
    "roce_adp_retrans",
    "out_of_sequence",
    "packet_seq_err",
    "local_ack_timeout_err",

    # 3. 软硬件交互与调度脱节 (Host-NIC 瓶颈)
    "out_of_buffer",
    "rnr_nak_retry_err",

    # 4. 内存保护与数据完整性 (致命硬件/内存错误)
    "req_cqe_error",
    "req_cqe_flush_error",
    "resp_cqe_error",
    "rx_icrc_encapsulated"
]

ETHTOOL_METRICS = [
    "rx_pause_ctrl_phy",
    "tx_pause_ctrl_phy",
    "rx_prio3_pause",
    "tx_prio3_pause"
]

# 用于计算吞吐的物理层字节数
THROUGHPUT_METRICS = [
    "rx_bytes_phy",
    "tx_bytes_phy"
]


def read_rdma_counters():
    counters = {}
    base_path = f"/sys/class/infiniband/{RDMA_DEV}/ports/{RDMA_PORT}/hw_counters/"
    for metric in RDMA_METRICS:
        filepath = os.path.join(base_path, metric)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    counters[metric] = int(f.read().strip())
            except Exception:
                counters[metric] = 0
    return counters


def read_ethtool_counters():
    counters = {}
    target_metrics = set(ETHTOOL_METRICS + THROUGHPUT_METRICS)
    try:
        result = subprocess.run(
            ["ethtool", "-S", NET_DEV], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                parts = line.strip().split(': ')
                if len(parts) == 2 and parts[0].strip() in target_metrics:
                    counters[parts[0].strip()] = int(parts[1])
    except FileNotFoundError:
        pass
    return counters


def main():
    parser = argparse.ArgumentParser(description="RDMA & Network HW Counters Monitor")
    parser.add_argument("-i", "--interval", type=float, default=1.0, help="Sampling interval in seconds (default: 1.0)")
    parser.add_argument("--csv", action="store_true", help="Output in CSV format (Rate per second)")
    args = parser.parse_args()

    interval = args.interval
    is_csv = args.csv

    if not is_csv:
        print(f"Monitoring {RDMA_DEV}/{NET_DEV} counters every {interval}s. Press Ctrl+C to stop.\n")
    else:
        # CSV 模式下打印表头
        headers = ["Timestamp", "TX_Gbps", "RX_Gbps"] + RDMA_METRICS + ETHTOOL_METRICS
        print(",".join(headers))

    prev_rdma = read_rdma_counters()
    prev_ethtool = read_ethtool_counters()

    try:
        while True:
            time.sleep(interval)
            
            curr_rdma = read_rdma_counters()
            curr_ethtool = read_ethtool_counters()
            
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

            # 计算物理层吞吐 (Gbps) = (Delta Bytes * 8) / (10^9 * interval)
            tx_bytes_delta = curr_ethtool.get("tx_bytes_phy", 0) - prev_ethtool.get("tx_bytes_phy", 0)
            rx_bytes_delta = curr_ethtool.get("rx_bytes_phy", 0) - prev_ethtool.get("rx_bytes_phy", 0)
            
            # 避免出现负数（硬件计数器极少数情况溢出清零时）
            tx_bytes_delta = max(0, tx_bytes_delta)
            rx_bytes_delta = max(0, rx_bytes_delta)

            tx_gbps = (tx_bytes_delta * 8) / (1e9 * interval)
            rx_gbps = (rx_bytes_delta * 8) / (1e9 * interval)

            if is_csv:
                row = [timestamp, f"{tx_gbps:.3f}", f"{rx_gbps:.3f}"]
                # CSV 输出平均速率 (每秒增量)
                for metric in RDMA_METRICS:
                    delta = max(0, curr_rdma.get(metric, 0) - prev_rdma.get(metric, 0))
                    rate = delta / interval
                    row.append(f"{rate:.2f}" if isinstance(rate, float) and not rate.is_integer() else str(int(rate)))
                for metric in ETHTOOL_METRICS:
                    delta = max(0, curr_ethtool.get(metric, 0) - prev_ethtool.get(metric, 0))
                    rate = delta / interval
                    row.append(f"{rate:.2f}" if isinstance(rate, float) and not rate.is_integer() else str(int(rate)))
                
                print(",".join(row))
            
            else:
                print(f"[{timestamp}] Counters Update (Interval: {interval}s) | Throughput: TX {tx_gbps:.2f} Gbps, RX {rx_gbps:.2f} Gbps")
                
                # 打印 RDMA 指标
                for metric in RDMA_METRICS:
                    delta = curr_rdma.get(metric, 0) - prev_rdma.get(metric, 0)
                    if delta >= 0:
                        print(f"  [RDMA] {metric}: +{delta} (Avg: {delta/interval:.1f}/s) (Total: {curr_rdma.get(metric, 0)})")
                
                # 打印 Ethtool 指标
                for metric in ETHTOOL_METRICS:
                    delta = curr_ethtool.get(metric, 0) - prev_ethtool.get(metric, 0)
                    if delta >= 0:
                        print(f"  [ETH]  {metric}: +{delta} (Avg: {delta/interval:.1f}/s) (Total: {curr_ethtool.get(metric, 0)})")
                
                print("-" * 60)

            # 更新基准值
            prev_rdma = curr_rdma
            prev_ethtool = curr_ethtool

    except KeyboardInterrupt:
        if not is_csv:
            print("\nStopped.")

if __name__ == "__main__":
    main()
