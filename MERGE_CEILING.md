# 合并上限实测报告

**日期**：2026-10-24
**方法**：先在 `/tmp/rehearsal` 的克隆副本里演练（逐层测量），再在工作区执行同样的合并并验证。
**状态**：**已完成**。工作区提交 `774ef34`，422 passed / 3 skipped，全部门禁通过，未 push。
**结论**：上限**可达**，成本远低于估计。真正的语义冲突只有 **3 处**，不是 15 处。

---

## 1. 结论

| 指标 | 初判 | 实测 | 差异原因 |
|---|---|---|---|
| 冲突文件数 | 9 | **9** | 属实 |
| 冲突块 | 15 | **3 处真实语义冲突** | 大部分是换行符造成的假冲突 |
| 大文件合并 | "手工活很大" | **`forge.py` 可脚本化重建** | 远端只加 2 个函数，未删改任何函数 |
| 总成本 | "当日大概率做不完" | **约 1–2 小时** | — |

**关键发现：`verify_TEMPLATE.py` 的"3563 行全量冲突"是我自己造成的换行符污染，不是真实内容差异。**

---

## 2. 换行符污染（本次最大的成本来源）

```
fa9df6a (base)      CRLF 1755 行
HEAD    (本地)      CRLF    0 行   <- 我把整个文件转成了 LF
up/main (远端)      CRLF 1892 行
```

我在改 `verify_TEMPLATE.py` 时编辑器把 CRLF 写成了 LF，于是 git 认为**每一行都变了**：

- 表面差异：`git diff --stat` 报 +1808/-1755（3563 行）
- 真实差异：统一换行符后 **278 行**

归一化后重新三方合并，冲突从 2 个巨型块（1194 行 / 1185 行）降到 **4 个普通块**。

> 教训：改 Windows 来源的文件前先确认 `.gitattributes`。仓库里没有该文件，所以 git 不做换行符归一化，这类污染会直接进 diff。

---

## 3. `forge.py`：可完全脚本化重建

三方函数级对比：

| | 相对 base 的变化 |
|---|---|
| base | 15 个函数 |
| 本地 | **+1**：`fork_verify_for_target` |
| 远端 | **+2**：`find_main_tex`、`fork_verify_generic` |

**没有任何函数被删除或改名，`_substitute_verify` 远端完全没动**（只有本地加了 `include_extended` 参数）。

因此正确解法不是"解冲突"，而是**以本地为基底，注入远端那 2 个函数**。已实测成功：

```
final defs: ['_read_template', '_format_simple_value', '_format_c1_symbols',
 '_format_c2_families', '_format_c6_blacklist', '_substitute_verify',
 '_substitute_compile', '_unicode_to_python_repr', '_format_replacements_block',
 '_substitute_fix_unicode', '_write_target', 'find_main_tex',
 'fork_verify_generic', 'fork_verify', 'fork_verify_for_target',
 'fork_compile', 'fork_fix_unicode', 'fork_all']
pyflakes: clean
```

18 个函数齐全，pyflakes 干净。

---

## 4. 真正的语义冲突：只有 3 处，全在 `.bbl` 附近

两边**独立实现了同一个功能**（`.bbl` 书目支持），所以必然撞车。

### 4.1 正则表达式（`_BBL_KEY_RE`）

| | 实现 |
|---|---|
| 本地 | `r'\\bibitem\s*(?:\[(?:[^\]\[]\|\[[^\]]*\])*\])?\s*\{\s*([^}\s]+)\s*\}'` + `re.DOTALL` |
| 远端 | `r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{\s*([^}\s]+)\s*\}'`（无 DOTALL） |

**实测对比**（5 个用例）：

| 用例 | 本地 | 远端 |
|---|---|---|
| `\bibitem{key1}` | key1 | key1 |
| `\bibitem[Author(2020)]{key2}` | key2 | key2 |
| 标签跨行 | key3 | **key3**（`\s*` 已允许跨行） |
| `\bibitem[[1]]{key4}` | key4 | **MISS** |
| `\bibitem[see [Smith 2020]]{key5}` | key5 | **MISS** |

**结论修正**：我最初判断"远端在跨行标签上会漏"是**错的**——`\s*` 本身就允许跨行，不需要 DOTALL。两者唯一差异是**标签内含方括号**（`[[1]]`、`[see [Smith 2020]]`）。

这类标签在真实 `.bbl` 里罕见（不是 natbib 的常规输出）。所以：

**处置**：保留本地正则（多覆盖一种形态，无额外代价），但**不要**把它写成"远端有 bug"——那是不成立的表述。

### 4.2 `_bib_keys` 文档字符串

纯注释差异，取信息量更大的本地版。

### 4.3 报告输出行

| | 实现 |
|---|---|
| 本地 | `print(f'Refs:   {bib_key_count} entries in {REFS.name}')` |
| 远端 | `if bib is None: print('Refs:   none found (no .bib or .bbl)') else: ...` |

**远端更好**：区分"没找到书目"与"找到 0 个键"。本地只是修了硬编码 `refs.bib`。

**处置**：合成为一版——远端的 `None` 分支 + 本地的 `REFS.name`。

---

## 5. 可达上限的完整清单

按实测，合并后应同时具备：

| 能力 | 来源 |
|---|---|
| `Target` 协议、`--target`、`admission` | 本地 |
| `--paper-dir` 通用审计、`fork_verify_generic` | 远端 |
| CI pyz 新鲜度门禁（`_check_pyz_fresh.py`） | 远端 |
| `_exclude_byproducts`（比我的 `ignore_patterns` 多排 `.egg-info`） | 远端 |
| `detector.yaml` 打包 | 两边都有，取远端简洁版 |
| `.bbl` 正则（跨行标签） | 本地 |
| `Refs: none found` 分支 | 远端 |
| 25/25 语料回归 | 本地 |
| `--version` 顶层参数 | 本地（远端没有） |

**这就是上限：全部可达，无需放弃任何一方能力。**

---

## 6. 剩余的硬约束（2026-10-24 晚已全部裁决）

以下不是冲突，是必须做的决定。五条现在都有结论：

1. **版本号** → **统一为 0.6.0**。理由：PyPI 上只有 0.5.0 / 0.5.1，CHANGELOG 却声称 0.5.2 已发布；直接发 0.7.0 会留下 0.5.2 与 0.6.0 两个空洞。重编号为 `--target`/`admission` → 0.6.0、`--paper-dir`/generic fork → 0.5.3、0.5.2 标注「尚未上 PyPI」。
2. **0.5.2 是否补发** → **不单独补发**，与 0.6.0 一同发布，CHANGELOG 里如实标注。
3. **`tmaudit.pyz` 二进制冲突** → 已用 `_build_pyz.py` 重建（89,357 字节，无 bytecode，含 `target_config.py`）。
4. **`verify_TEMPLATE.py` 的换行符** → 合并产物保持 CRLF（1927 行），已核对。
5. **`_substitute_verify` 的 `include_extended`** → 已实测：`fork_verify_generic` 生成的脚本正常，`--paper-dir` 端到端 6 findings 通过。

### 6.1 ⚠️ `_check_all_regressions.py` 有副作用（重要）

该脚本注入 bug 验证回归有效性，**但恢复步骤不完整**：

- 会把 `forge.py` 恢复成 16 defs（丢掉 `find_main_tex`、`fork_verify_generic`）
- 会把 `verify_TEMPLATE.py` 恢复成合并前的 1813 行 LF 版本（丢掉 `_resolve_bib`）
- 结果是 `AttributeError` 一片，而脚本仍打印 "14/14 bugs are correctly caught" 并以 rc=1 退出

**结论：只在一次性克隆里跑它，或跑完立即 `git checkout` 恢复。本次踩到两次，第二次才发现问题出在脚本而不在我的合并。**


---

## 7. 验证状态（已补齐）

本节原先标注三项未做，**现已全部完成**，详见 §9：

- ~~未跑合并后的测试套件~~ → 工作区 422 passed / 3 skipped
- ~~未验证 `--paper-dir` 与 `--target` 同时存在时的行为~~ → 已实测五种组合（§9.2）
- ~~未重建 dist 与 pyz~~ → 已重建，`twine check` 双包 PASSED

以上是**合并可行性**与**合并产物可用性**两轮实测的结果，两者都已落地。


---

## 8. 已完成的演练动作（在 `/tmp/rehearsal`，未触碰工作区）

| 文件 | 处置 | 状态 |
|---|---|---|
| `_build_pyz.py` | 取远端（`_exclude_byproducts` 更全） | 已解 |
| `pyproject.toml` | 版本取 0.7.0 + 保留 yaml 行 | 已解 |
| `src/tmaudit/__init__.py` | 用法文档并列三入口 + 版本 0.7.0 | 已解 |
| `src/tmaudit/cli.py` | 三入口互斥逻辑（见下） | 已解 |
| `src/tmaudit/forge.py` | 以本地为基底注入远端 2 函数 | 已解，18 函数齐全，pyflakes 干净 |
| `verify_TEMPLATE.py` | 归一化换行符后解 4 处真实冲突 | 已解，CRLF 保持 |
| `CHANGELOG.md` / `README.md` | CHANGELOG 重排版本序；README 取并集重排 | 已解 |
| `tmaudit.pyz` | 用 `_build_pyz.py` 重建 | 已重建，89,360 字节 |

---

## 9. 工作区合并完成（2026-10-24 21:30）

工作区 `~/project-review-20261013/verify/tmaudit` 已执行同样的合并，提交为
`774ef34`（真合并，两父），工作区干净，`behind=0`，`ahead=4`。**未 push、未 tag、未上传。**

合并前建了备份分支 `backup/before-merge-20261024-2111`。

### 9.1 全部门禁（工作区实测）

| 门禁 | 结果 |
|---|---|
| `pytest` | **422 passed, 3 skipped, 0 failed** |
| `_check_pyz_fresh.py` | `OK: tmaudit.pyz matches src/tmaudit/ (21 files, no bytecode)` |
| `_check_yaml.py` | `[OK] ci.yml is valid YAML with expected structure`（含新增 build 步骤） |
| `_check_github_templates.py` | `44/44 OK` |
| `twine check dist/*` | `tmaudit-0.6.0-py3-none-any.whl` / `.tar.gz` 均 PASSED |
| 干净 wheel 安装 | `tmaudit 0.6.0`；`detector.yaml` 随包；端到端 `--paper-dir` 审计 6 findings 通过 |

**422 > 演练副本的 391**：工作区有 `case-studies/arxiv-corpus/_corpus`，那 3 个语料回归测试真的跑了并通过。3 个 skip 仍需 `PAPER{1,5}_CONSOLIDATED` 与 `_verify_TEMPLATE.py`（不在仓库里）。

### 9.2 功能共存实测

| 场景 | 结果 |
|---|---|
| `--paper` + `--paper-dir` | 报错退出，互斥生效 |
| `--paper-dir` 单独 | 生成 `verify_generic.py`，6 findings，rc=0 |
| `--target` + `--paper-dir` | 允许；`--target` 生效，`--paper-dir` 当落盘目录 |
| pyz 三入口 | `verify --paper-dir` / `verify --target --dry-run` / `admission` 全部正常 |
| `admission --gain 7.3 --tasks 89` | `m >= 2,593`，与 CHANGELOG 记载一致 |

### 9.3 合并中查出的两个发布级缺陷（已修）

1. **wheel 缺 `detector_config/detector.yaml`** — 非 editable 安装会静默回落内置默认值。远端 0.5.2 已独立修过（`02ca4c3`），属重复踩坑；根因是 push 前未先 `git fetch` 比对 `origin/main`。
2. **`tmaudit.pyz` 缺 `target_config.py`** — 零安装路径根本到不了 `--target`。

### 9.4 假绿教训（本报告最重要的一条）

两次跑出「全绿」都是假的：

- 第一次：`forge.py` 的两个远端函数在合并验证时存在，却**从未进入索引** → `AttributeError`
- 第二次：`verify_TEMPLATE.py` 被换成 HEAD 旧版（1813 行），远端 `_resolve_bib` 全丢

第二次的元凶是 `_check_all_regressions.py` 的恢复步骤（见 §6.1），第一次是真漏。

**判定方法**：`git show :<path> | grep -c '^def '` 对比工作区；`grep -c '<两侧独有符号>'` 三版对齐（HEAD / origin/main / worktree）。`forge.py` 应为 18 defs、模板应含 `_resolve_bib` 与 `OBSERVATION_FAILURES`。**测试通过不等于合并正确。**

### 9.5 本轮一并处理的三件遗留

1. **CHANGELOG 错位的 `[Unreleased]`** → 移到 0.4.0 之后，改标题为 `## [0.4.x maintenance] — after 0.4.0`。那段的实际内容（docs issue 模板、`_check_github_templates.py`、CI job）早已交付，标 `[Unreleased]` 是谎称未发布。
2. **CI 不跑打包测试** → 在 pytest 前加 `python -m build`，`tests/test_package_data.py` 不再跳过（本地实测：无 dist 时 2 skip，build 后 5/5 全过）。
3. **版本号** → 统一 0.6.0（详见 §6）。

### 9.6 仍遗留

- `tests/test_package_data.py` 的 2 个测试现在 CI 会跑，但只在那一步之后；`audit-all` 等其它 job 不构建产物，不受影响。
- PyPI 尚未发布 0.6.0。上传是独立动作，需你明确批准。


### 三入口互斥的设计（已写入演练副本）

```python
has_target = getattr(args, 'target', None) is not None
chosen = sum((
    args.paper is not None,
    args.paper_dir is not None and not has_target,
    has_target,
))
if chosen > 1:
    print('ERROR: --paper, --paper-dir and --target are mutually exclusive')
    return 2
if has_target:
    # --paper-dir 在此只表示落盘目录，不表示被审对象
    return _verify_external_target(args)
```

理由：三者语义是"控制权递增"——`--paper` 用整套规则包，`--paper-dir` 换文档不换规则，`--target` 文档和规则都换。同时给两个会让人无法预判哪个生效，所以报错而非定优先级。
