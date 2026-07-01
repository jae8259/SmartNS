# Source Origins

This document traces the upstream origin of each subsystem under `src/` and `include/`.

## Summary Table

| Subsystem | Files | Origin |
|---|---|---|
| `src/rxe/` | rxe_opcode.c, rxe_req.cpp, rxe_recv.cpp | Linux kernel `drivers/infiniband/sw/rxe/` |
| `src/devx/` + `include/fw/` | devx_device.cpp, devx_mr.cpp, mlx5_prm*.h | NVIDIA DOCA SDK (Copyright NVIDIA) |
| `src/dma/` | dma.cpp | SmartNS original (mlx5dv self-connected QP) |
| `src/rdma_cm/libr.cpp` | libr.cpp | perftest-style libibverbs boilerplate |
| `src/rdma_cm/libsmartns.cpp` | libsmartns.cpp | SmartNS original (forked rdma-core) |
| `src/raw_packet/` | raw_packet.cpp | SmartNS original |
| `src/tcp_cm/` | tcp_cm.cpp | SmartNS original (POSIX sockets) |
| `src/dpu/` | config/controlpath/datapath/main.cpp | SmartNS original (core contribution) |


## `src/rxe/` — RoCE Protocol Engine

**Origin: Linux kernel [`drivers/infiniband/sw/rxe/`](https://github.com/torvalds/linux/tree/master/drivers/infiniband/sw/rxe)**

The RXE (RDMA over Ethernet eXtension) subsystem is the Linux kernel's software implementation of RoCE (Soft RoCE). SmartNS extracts this protocol logic from the kernel and runs it in userspace on the DPU ARM cores.

| SmartNS file | Kernel counterpart |
|---|---|
| `src/rxe/rxe_opcode.c` | [`drivers/infiniband/sw/rxe/rxe_opcode.c`](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_opcode.c) |
| `src/rxe/rxe_req.cpp` | [`drivers/infiniband/sw/rxe/rxe_req.c`](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_req.c) |
| `src/rxe/rxe_recv.cpp` | [`drivers/infiniband/sw/rxe/rxe_recv.c`](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_recv.c) |
| `include/rxe/rxe_opcode.h` | [`drivers/infiniband/sw/rxe/rxe_opcode.h`](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_opcode.h) |
| `include/rxe/rxe_hdr.h` | [`drivers/infiniband/sw/rxe/rxe_hdr.h`](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_hdr.h) |
| `include/rxe/rxe_param.h` | [`drivers/infiniband/sw/rxe/rxe_param.h`](https://github.com/torvalds/linux/blob/master/drivers/infiniband/sw/rxe/rxe_param.h) |

Confirming constants that match the kernel exactly:
- `RXE_MAX_PKT_PER_ACK = 64`
- `RXE_MAX_UNACKED_PSNS = 128`
- `psn_compare()` — identical signed PSN arithmetic
- `rxe_opcode_info` table — all RC opcodes with mask/length/offset

`rxe_req.cpp` and `rxe_recv.cpp` are C++ rewrites of the kernel's C files, adapted to work with SmartNS data structures (`dpu_qp`, `dpu_send_wqe`, `datapath_handler`) instead of kernel `rxe_qp` / `rxe_buf`.

---

## `src/devx/` and `include/fw/` — Firmware-Level NIC Programming

**Origin: [NVIDIA DOCA SDK](https://docs.nvidia.com/doca/sdk/) (private, NVIDIA CORPORATION & AFFILIATES)**

The DevX layer talks directly to BlueField-3 firmware via `mlx5dv_devx_general_cmd`. The code and constants come from NVIDIA's DOCA SDK internals.

Evidence:
- `include/fw/mlx5_prm.h`, `include/fw/mlx5_prm_manual.h`, `include/fw/multi_os_prm.h` all carry the header:
  ```
  Copyright (c) 2022/2024 NVIDIA CORPORATION & AFFILIATES, ALL RIGHTS RESERVED.
  This software product is governed by the End User License Agreement...
  ```
- All constants prefixed `PRIV_DOCA_MLX5_*` (e.g., `PRIV_DOCA_MLX5_MKC_ACCESS_MODE_MTT`, `PRIV_DOCA_MLX5_HCA_CAP_OP_MOD_GENERAL_DEVICE`) are from the DOCA private header namespace.
- Comment style in `devx_device.cpp` ("Set operation code", "Send the command to FW using DevX", "Inspect the returned status", "Translate the capabilities from PRM format") matches DOCA SDK sample verbatim.

`src/devx/devx_mr.cpp` implements three cross-vhca memory key variants that are specific to DOCA BlueField programming:
- **alias mkey** (`devx_create_alias_memory_region`) — lets the DPU create an alias to a host-registered MR
- **crossing-vhca mkey** (`devx_create_crossing_vhca_mkey`) — lets the DPU directly address the full host memory space
- **indirect mkey / KLM** (`devx_create_indirect_mkey`) — scatter-gather memory key for non-contiguous host buffers

These are the mechanism that enables zero-copy: payload arrives at the DPU NIC and is DMA'd straight into the host application's MR without host CPU involvement.

---

## `src/dma/` — DMA Engine

**Origin: SmartNS original, using MLNX_OFED `mlx5dv` API**

No direct upstream copy. This is SmartNS-specific code that uses the `MLX5DV_QP_EX_WITH_MEMCPY` capability introduced in MLNX_OFED for BlueField.

Key technique — **self-connected RC QP**:
- A single RC QP connects to itself (`dest_qp_num = qp->qp_num`)
- Configured with `mlx5dv_memcpy` send operation
- Used to issue RDMA Writes from the DPU's RX packet buffer into the host application memory using the cross-vhca mkeys from `devx/`
- `get_mmo_dma_max_length()` queries the NIC's hardware memcpy engine (MMO) maximum transfer size

---

## `src/rdma_cm/` — RDMA Connection Management

Two files with different origins:

### `libr.cpp` — libibverbs Utility Wrappers

**Origin: Adapted from [`perftest`](https://github.com/linux-rdma/perftest) (linux-rdma/perftest)**

Functions like `ctx_find_dev`, `ctx_open_device`, `ctx_open_devx_device`, and the RC QP creation helpers closely follow the patterns in the `perftest` benchmark suite (used across the RDMA community for QP bringup boilerplate). No copyright header present, suggesting it was written by the SmartNS authors in the perftest style.

### `libsmartns.cpp` — SmartNS Host-Side Shim

**Origin: SmartNS original, built on forked `rdma-core`**

Wraps the standard libibverbs API with SmartNS-aware equivalents (`smartns_open_device`, `smartns_alloc_pd`, `smartns_reg_mr`, etc.). These route through the SmartNS kernel module instead of the normal kernel path. Depends on the forked `rdma-core` at `third_party/rdma-core` → [`github.com/cxz66666/rdma-core`](https://github.com/cxz66666/rdma-core) (itself a fork of [`linux-rdma/rdma-core`](https://github.com/linux-rdma/rdma-core)).

---

## `src/raw_packet/` — Packet Header Construction

**Origin: SmartNS original**

No upstream copy. Two responsibilities:
- **`calculate_soft_rss()`** — software Toeplitz hash that mirrors the NIC's hardware RSS so the DPU can predict which RX queue an inbound packet will land on. The Toeplitz algorithm itself is a standard network algorithm, not specific to any project.
- **`init_udp_packet()`** — fills static Ethernet/IPv4/UDP header fields into pre-allocated hugepage TX buffers. Only the PSN and payload pointer change per packet at line rate.

---

## `src/tcp_cm/` — Bootstrap TCP Connection

**Origin: SmartNS original, generic POSIX sockets**

Plain BSD socket code (POSIX `getaddrinfo` / `connect` / `accept` / `read` / `write`). Used only during startup to exchange QP numbers, GIDs, vhca IDs, and memory keys between host and DPU. No external upstream.

---

## `src/dpu/` — Core SmartNS DPU Runtime

**Origin: SmartNS original**

The primary contribution of SmartNS. Four files:
- `config.cpp` — loads compile-time server/client MAC and IP config
- `controlpath.cpp` — receives control commands from the host (`OPEN_DEVICE`, `CREATE_QP`, `DESTROY_QP`, `MODIFY_QP`) and creates/tears down the corresponding DPU-side QP state
- `datapath.cpp` — initialises hugepage TX/RX buffers, installs flow-steering rules to steer RoCE UDP packets to the right core, and drives the per-core packet processing loop
- `main.cpp` — entry point, forks controlpath and datapath threads

---
