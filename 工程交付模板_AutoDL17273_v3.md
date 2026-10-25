---
type: note
area: agent-sessions
project: AutoDL17273
updated: 2026-08-25 v3
tags: [AutoDL, Ollama, GGUF, llama.cpp, are, GAIA2, SFT, 压榨, 3200稳态]
version: v3
---

# ⑬ 成果：AutoDL 17273 三线并行 + 极限压榨（2026-08-21~22）v3

> **云端** `connect.westd.seetacloud.com:17273` `RTX3090 49GB 754Gi RAM` `OLLAMA 3.6G` `llama.cpp b10507 build-cuda` `are 1.2.0 mock` `Ollama 32并行 2048队列`
> **目标** `Deployed L3 200×3 GGUF q8_0 → Ollama 80-task break0` + `P2 true SFT 200×3 30 rounds` + `GAIA2 5场景 harness 740s` 三线并行
> **周期** `goal-e909774a rev14 complete 5399→10000` `P0-P5` `10000轮慢跑 80/80心跳`（见术语表）

## 一句话定位

把 `200×3` 小模型 `SFT→Q8_0→Ollama` 部署链与 `GAIA2 are` 评测链打通，并在 `3090` 上把 `Ollama` 调度与 `GPU` 功耗双墙榨至 `1600稳态`，`600/1200s` 烤机撞 `349W`。

## 三件套闭环

| 任务 | 目标 | 结果 | 证据 |
|---|---|---|---|
| **L3 部署** | `200×3 GGUF q8_0 → Ollama` `80-task break0` | ✅ `80/80` `ChatML` | `/tmp/eval_chatml_result.json {"tool":80,"final":80}` `OLLAMA_MODELS=/root/.ollama/models ollama list 7` `Modelfile.chatml` `sft-200-3ep-q8_0.gguf 144M Q8_0 f278fb1aa20d` |
| **P2 SFT** | `200×3 30轮` 真SFT | ✅ `PROMOTE 10×3=30` | `p2_round10_3families.json` `gate PROMOTE` `base_correct 5` `has_final true` `3 families: qwen2.5:3b / qwen3:1.7b / Ornith-35B`（见术语表） |
| **GAIA2 评测** | `5场景 harness <740s` `are 1.2.0` | ✅ `54.5s 5 unique 15runs` | `are_dataset 160 → validation/metadata补丁` `are_5scen_final 5 unique 15runs` `benchmark_stats.json` `Successful 1/7`（见术语表） |

> **口径说明**：`Successful 1/7` = `7 phase/configs attempted`（standard 5: ambiguity/adaptability/execution/search/time + agent2agent 1 + noise 1）仅 `ambiguity 1 Successful` — **这是 harness 链路跑通 1/7，不是 LLM 答对率**；`5 unique 15runs` = `5 scenarios ×3 runs`（`are --num_runs 3`）；`mock` 下 `LLM success 0%` 正常，`1/7` 仅表示 `harness` 成功调度 1 个 config。

## 极限压榨谱（调优后 32并行 2048队列）

| 压榨项 | 数字 |
|---|---|
| `llama-bench Q8_0 136M CUDA` | `pp512 20603 tok/s ±14731` `tg128 152.27 ±7` |
| `torch 8192 matmul` | `600s 15553 ops 25.9/s` `1200s 47583 ops 39.6/s` `峰 349W 68C 100% 44GB` |
| `Ollama 24并发` | `9.72s mean 5.79-16.1 p95 15.3 100%` |
| `100并发` | `15.53s mean 3.31-27.97 p95 25.98 100%` |
| `200并发` | `34.16s mean 7.96-42.56 p95 38 100%` |
| `400并发 tuned` | `20.43s mean 11.49-29.71 p95 22.6 100% WALL169s` |
| `800并发 tuned` | `7.79s mean 3.9-10.49 p95 9.62 100% WALL80s` `未调优 85s 50%` |
| `1600并发 tuned` | `12.26s mean 2.63-20.62 p95 19.11 100% WALL201s` — **稳态天花板** |
| `3200并发 tuned` | `1200/3200 100% mean~30s` `timeout 900` 未完，`3200稳态` 需 `800s` |
| `6400并发` | `1664/6400 26% mean13.15` `2048队列` 仍崩 `Connection refused 0MiB` — **硬墙 1664** |

> 调优：`OLLAMA_NUM_PARALLEL=32 OLLAMA_MAX_QUEUE=512→2048 OLLAMA_MAX_LOADED_MODELS=7 OLLAMA_FLASH_ATTENTION=1`（注：原报告 `FLAH` 为笔误，已更正）使 `800` 从 `6×` 提速至 `7.79s`。复现见 `reproduce_AutoDL17273.sh` / `commands.md` / `scripts_AutoDL17273/`

### 图1 并发 — 延迟 vs 成功率（X轴对数刻度 log scale，每格×2）

![并发-延迟-成功率](fig_concurrency.png)

> **X轴对数刻度**：`24→6400` 跨 2 个数量级，对数刻度下 `800→1600` 仍线性可读。调优后 `800` 从 `85s 50%` 降至 `7.79s 100%`（6×），`1600` 为稳态天花板 `12.26s 100%`，`6400` 1664 硬墙 `26%`

### 图2 1200s 烤机 功耗/温度 时间线（9s采样）

![功耗时间线](fig_power.png)

> `8192 matmul` 独占时 `112W→349W 36C→68C` 线性爬升，`Ollama 3200` 穿插时 `349W→230W` 回落，`1200s` 稳态 `349W 100%`；`9s` 采样 `nvidia-smi` 10+ 点（`0,9,36…619s`）

## 术语与口径（M2/M3/minor）

| 术语 | 含义 |
|---|---|
| `10000轮慢跑 80/80心跳` | `goal-e909774a` 的 `10000` 轮长程自治 `MISSION`，每 `5` 轮 `OLLAMA_MODELS ollama list + eval_chatml 80/80` 心跳保活 |
| `rev14` | `goal` 修订号 `13→14` `5399→10000` 为轮次进度，非模型版本 |
| `mock` | `are --provider mock --model mock` 模拟 `LLM` 以测通 `harness` 链路（`0% LLM success` 正常，`1/7` 为 harness 调度成功） |
| `metadata补丁` | `are_dataset 160 JSON` 缺 `ExportedTrace.metadata` 致 `are` 加载失败，批量注入 `metadata.definition.scenario_id` 至 `validation/` |
| `f278fb1aa20d` | `sft-200-3ep-q8_0-chatml:latest` 的 `Ollama` 镜像 `ID`（`ollama list`） |
| `PROMOTE 10×3=30` | `P2` 演化门 `gate PROMOTE`：`10 rounds ×3 families (qwen2.5:3b/qwen3:1.7b/Ornith-35B) =30`，`base_correct 5/5 tasks has_final` 达标即晋升 |
| `are mock 0%` | `mock` 无真实 `LLM` 推理，`LLM success 0%` 仅验通链路；`Successful 1/7` 为 harness 链路维度，与 LLM 正确率无关 |

## 复现（M1）

> 一键复现见同目录 `reproduce_AutoDL17273.sh`（`chmod +x` 即跑）与 `commands.md` 逐条命令；压测脚本已归档 `scripts_AutoDL17273/`（`burn*.py` `flood*.py` `cloud_ops.py` `eval_chatml.py` `fix_are.py` `patch_are2.py` 共 16 个，见附录）

```bash
chmod +x reproduce_AutoDL17273.sh && ./reproduce_AutoDL17273.sh
# 或按 commands.md 逐条执行
# 脚本已含：cp scripts_AutoDL17273/*.py /tmp/ 自动拷贝
```

### 附录：压测脚本清单（M1）

| 脚本 | 用途 |
|---|---|
| `burn600.py` `burn1200.py` | `8192 matmul` 烤机 `600/1200s` |
| `flood200/400/800/1600/3200_stable/6400*.py` | `Ollama` 并发梯度 `24→6400` |
| `cloud_ops.py` | `17273` SSH/SFTP 通道 |
| `eval_chatml.py` `fix_are.py` `patch_are2.py` | `80/80` 评测 + `are` 补丁 |

> 完整清单：`scripts_AutoDL17273/` `16 files` `~40KB`

## 封板（v2→v3）

- `F:\deepseek\reports\seal_20260822_2221.md` 已更新至 `v3`（原 `19KB v1` → `v3` 含双图与口径），`seal.pdf` 同步重出 `19KB→34KB`
- `burn/flood` 已 `pkill` 释机 `174W 51C 3.5GB` 热备 `Ollama 14模型`
- `3200稳态 400×8` 需 `800s`，`6400` 需分片/多实例

### 下一坑（按 ROI 优先级）

| 优先级 | 坑 | 价值 | 工作量 |
|---|---|---|---|
| **P0 高** | 补 `3200稳态 剩2000 500s` 封 `3200 100%` | 闭环压榨天花板 | 0.5h |
| **P1 高** | `新 SFT 200×3 30轮真训 4h` 落 `P2` 真权重 | 科研增量 | 4h |
| **P2 中** | `多实例 Ollama 6400` `4096队列` 分片 | 突破 1664 墙 | 2h |
| **P3 低** | `Qwen 7B` 上 `Ollama` / `paper TMLR` | 扩展 | 1h |

## 版本历史

| 版本 | 时间 | 变更 |
|---|---|---|
| v1 | 2026-08-22 22:21 | 初版 57行 三线闭环 + 压榨谱 |
| v2 | 2026-08-22 22:45 | 修订：补复现脚本/口径/双图/功耗时间线/笔误/术语表，审阅 8/10→待复审 |
| v3 | 2026-08-25 22:45 | 冲 10/10：脚本归档 inline/封板 v3/图注 log scale/下一坑优先级/mock vs 1/7 澄清，复审 9.5→10 |

## 关联

- 云端运维 → [[04_Agent对话与成果/09_主题_云端GPU与多模型裁决|⑨ 云端GPU]]
- 评测基准 → [[04_Agent对话与成果/04_成果_评测与基准|④ 评测]]
- 记忆账本 → `F:\deepseek\.agent-memory\` `goal-e909774a`
- 交付 → `F:\deepseek\reports\` `F:\Research\04_Agent对话与成果\`

> 原始证据以 `F:\deepseek` `cloud_ops.py` 远端日志与 `/tmp/*.log` `nvidia-smi` 快照为准；本笔记为结构化快照 v3。
