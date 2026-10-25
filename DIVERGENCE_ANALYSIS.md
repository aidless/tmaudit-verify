# 分叉分析：本地 0.7.0 vs origin/main 0.5.2

**日期**：2026-10-24
**状态**：仅分析。未合并、未 push、未上传任何索引。

---

## 0. 结论先说

本地与 `origin/main` 不是"同一件事的两个进度"，而是**两次平行的独立演进**，从同一个基点 `fa9df6a` 分出去走了两天。

- 双方**独立地**修了同一批缺陷（`.bbl` 支持、版本漂移）。
- 远端另有本地完全没有的能力（CI 门禁、`detector.yaml` 打包修复、`--paper-dir` 通用路径、发布文档）。
- 本地另有远端完全没有的能力（`Target` 协议、`--target`、`admission`）。

两者是**互补**的，不是竞争关系。但直接 merge 的冲突面很大：**9 个文件双边都改**。

---

## 1. 分叉事实

| 项 | 值 |
|---|---|
| 合并基点 | `fa9df6a docs: validator check count is 44/44...` |
| 本地领先 | 2 个提交（`3d78dc7`、`e5bdc23`） |
| 远端领先 | **9 个提交**（`df9c1a3` … `3fd0e0f`） |
| 双边都改的文件 | **9 个** |

### 双边都改的文件（冲突候选）

```
CHANGELOG.md
README.md
pyproject.toml
src/tmaudit/__init__.py
src/tmaudit/cli.py
src/tmaudit/forge.py
src/tmaudit/templates/verify_TEMPLATE.py
tests/test_template_defaults.py
tmaudit.pyz
```

### 远端 9 个提交

| 提交 | 内容 | 与本地关系 |
|---|---|---|
| `df9c1a3` | `plugins run --paper-dir`：插件可指向任意论文 | 互补（本地做的是内置规则指向任意论文） |
| `80c40d7` | **CI：pyz 陈旧即失败** + `_check_pyz_fresh.py` | **本地完全没有**，且本地曾因此埋雷（见 §3） |
| `7400f81` | 修版本漂移（0.5.1） | **重复**，本地也修了（0.6.0） |
| `918eab1` | 通用 `verify --paper-dir`、`.bbl` 书目、真实论文 case study | **重复度高**：本地也做了 `.bbl` + 通用审计 |
| `c3d67b5` | 接管同步材料 + `.gitignore` | 互补 |
| `02ca4c3` | **release: 0.5.2** — 修 `detector.yaml` 未打包、相对 `--paper-dir` 二次解析 | **本地完全没有**（见 §4） |
| `8c57404` | launch 文档（长/短稿 + 预检清单） | 互补 |
| `575d01d` | CI 跑 Python 3.9 on ubuntu-22.04 | 互补 |
| `3fd0e0f` | 合并 CHANGELOG 里两个 Fixed 标题 | 纯文档 |

---

## 2. 测试文件：零重叠（这是好消息）

| | 基点 | 本地 | 远端 |
|---|---|---|---|
| tests/ 文件数 | 18 | 22 | 20 |

- **本地新增 4 个**：`test_admission.py`、`test_target.py`、`test_target_config.py`、`test_corpus_regression.py`
- **远端新增 2 个**：`test_check_pyz_fresh.py`、`test_verify_paper_dir.py`

两边新增文件**没有任何重名**。合并后测试文件应为 24 个，测试数应是本地的 394 加上远端新增的约 20–30 个。

---

## 3. 已发现并已修的实质性缺陷（本地侧，未提交）

### 3.1 pyz 内含 `.pyc`，会被远端 CI 直接判失败

`_build_pyz.py` 用 `shutil.copytree(PKG, target_pkg)` 复制包树，**没有排除 `__pycache__`**。

以前不出问题，是因为只在干净树上构建。但任何一次跑测试或 `pip install -e .` 都会在 `src/` 里留下字节码，于是：

- 归档从 85,512 字节虚增到 **157,418 字节**（近一倍是 `.pyc`）
- 带上的是**针对构建机解释器**编译的字节码
- 远端 `80c40d7` 的 `_check_pyz_fresh.py` 会**直接拒绝**这种归档

实测（用远端同一脚本校验）：

```
修复前：archive holds tmaudit/__pycache__/cache.cpython-313.pyc, which is not in src/tmaudit/
        ...（约 10 条）
修复后：OK: tmaudit.pyz matches src/tmaudit/ (21 files, no bytecode)
```

**已修**：`copytree` 加 `ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo')`，pyz 降到 85,512 字节，三项功能（`--version` / `admission` / `verify --target`）实测正常。

> 这条恰好证明远端 CI 那个门禁是有价值的：它会在推送时就拦住我这种错误，而不是等用户 `pip install` 之后发现 pyz 里有别人的字节码。

### 3.2 数据不一致：CHANGELOG 说 0.5.2 已发布，PyPI 上没有

```
远端 CHANGELOG:  ## [v0.5.2] — 2026-10-24
PyPI releases:   ['0.5.0', '0.5.1']
```

远端写了 0.5.2 的发布条目，但 `0.5.2` **从未上传到 PyPI**。这意味着：任何从 GitHub 读 CHANGELOG 的人都会以为 0.5.2 可装，实际装不到。

这条不阻塞本地发布，但**合并时必须处理**：要么补传 0.5.2，要么把 CHANGELOG 条目标注为"未发布"。

---

## 4. 远端有、本地完全没有的东西

按重要性排：

1. **CI pyz 新鲜度门禁**（`_check_pyz_fresh.py` + `tests/test_check_pyz_fresh.py` + ci.yml）。本地侧毫无对应物，且 §3.1 证明本地正需要它。
2. **`detector_config/detector.yaml` 打包修复**（`02ca4c3`）。`package-data` 漏了 `detector_config/*.yaml`，导致**非 editable 安装**的用户拿不到该文件而回落到内置默认值。

   **已核实：本地 0.7.0 的 wheel 有同一个 bug。** 证据：

   ```
   修复前 wheel 内容 : tmaudit/detector_config/{__init__.py, detector_min.py}   ← 没有 yaml
   已安装环境检查    : yaml installed: NONE
   修复后            : yaml installed: ['detector.yaml']
   ```

   已在本地修复（`pyproject.toml` 补 `detector_config/*.yaml`），并新增
   `tests/test_package_data.py`——它读**构建出的 wheel** 而非源码树，因为
   源码树里文件一直在，这正是该 bug 能藏两轮的原因。测试已确认能在这个坏
   wheel 上报错，修复后转绿。

   > 这条的分量：如果没有做这次分叉分析，这个 0.7.0 会带着一个"安装后行为
   > 与源码不一致"的缺陷发布出去，而全套 394 个测试都是绿的。
3. **相对 `--paper-dir` 二次解析修复**。本地无 `--paper-dir` 相关改动，但需确认本地 `--target` 路径没有同类问题。
4. launch 文档、Python 3.9 CI 矩阵。

**第 2 条必须核实**——它意味着我刚构建的 wheel 可能是坏的。

---

## 5. 本地有、远端完全没有的东西

1. **`Target` 协议**（`target.py`，380 行）：把被审对象从裸 `str` 解耦，插件可选择性接收 `Target` 而非 `str`。
2. **`--target FILE`**（`target_config.py`，520 行 + `forge.fork_verify_for_target`）：从磁盘加载外部 TOML/JSON 配置，走同一条 verify 路径。这是"陌生人能用"的核心。
3. **`admission`**（`admission.py`，481 行 + 41 测试）：arXiv:2610.18813 eq.(8)(9)(6) 的统计准入证书，stdlib-only。
4. **语料回归 25/25**：用已安装 wheel、零依赖，对 25 篇 arXiv 全量跑外部路径，0 崩溃、0 `[not observed]`、25/25 书目解析。
5. **`--version` 顶层参数**（远端是否已有需核实）。

---

## 6. 合并时会真正冲突的地方

不是文本冲突（那只是劳动量），而是**语义冲突**：

### 6.1 `cli.py`：`--paper-dir` 与 `--target` 的功能重叠

- 远端：`verify --paper-dir DIR` —— 用**内置规则**审任意目录里的论文
- 本地：`verify --target FILE` —— 用**外部配置**审任意论文

两者解决"陌生人怎么用"这个问题的不同层次：`--paper-dir` 只换被审对象，规则仍是内置 C1–C10；`--target` 连规则一起换。

合并后**不应二选一**，应共存：
- `--paper-dir`：我只想用你的规则审我的论文
- `--target`：我要连规则一起配

但两者的参数互斥校验、`forge` 的分支、退出码需要统一，这部分是手工活。

### 6.2 版本号

本地 0.7.0 / 远端 0.5.2。合并后正确版本取决于是否补发 0.5.2：

- 若补发 0.5.2 → 下一个是 **0.6.0**（本地是功能新增），本地 CHANGELOG 的两个大段要重新编号
- 若不补发 → 本地 0.7.0 可保留，但 CHANGELOG 里缺少 0.5.2 条目会造成跳跃

### 6.3 `verify_TEMPLATE.py`

双边都大改（本地 3563 行变更）。这是最大的一块手工合并。

### 6.4 `.bbl` 解析

双边各写了一份。必须**只保留一份**并确认远端测试（若有）也能过。

---

## 7. 建议路径（未执行）

按风险从低到高：

### 方案 A：先核实 §4.2，再决定

**第一步不是合并，是确认本地 0.7.0 的 wheel 是否漏了 `detector.yaml`。** 如果漏了，本地这个包本身就有 bug，不该上传。这一步 5 分钟可完成，且与是否合并无关。

### 方案 B：先把本地功能推到分支，不在 main 上合并

```bash
git switch -c feat/v0.7.0-target-admission
git push -u origin feat/v0.7.0-target-admission
# 在 GitHub 上开 PR 到 main，用 PR diff 来对齐两边
```

优点：main 保持与远端一致，不制造第二次分叉；PR 页面能逐文件看清重叠；CI 会在 PR 上跑（含 pyz 门禁）。

### 方案 C：本地 merge 后一次性发布

工作量最大：解 9 个文件的冲突 → 重跑全量测试 → 重建 pyz 与 dist → 确认 CI 逻辑 → 统一版本号 → 再上传。**当日做不完的概率较高**。

---

## 8. 与"上 TestPyPI"这个原始目标的关系

原始目标是走一遍 TestPyPI 验证发布链。这个目标**不依赖合并**：

- TestPyPI 是独立索引，`tmaudit` 在它上面是 404（从未发布）
- 本地 0.7.0 的 wheel 已在干净环境通过三项功能验证
- 上传 TestPyPI 不消耗正式版本号

**唯一前置**是 §7 方案 A 那一项核实。

---

## 9. 待你决策

1. ~~`detector.yaml` 是否在本地 wheel 里？~~ **已查并已修**：不在，现已补入并加测试守住。
2. 合并走 A / B / C 哪条？
3. 0.5.2 要不要补发到 PyPI，还是把 CHANGELOG 标为未发布？

---

## 10. 本轮已完成的动作（未提交、未联网发布）

| 动作 | 结果 |
|---|---|
| 修 `_build_pyz.py` 的 `__pycache__` 泄漏 | pyz 157,418 → **85,512 字节**，远端 CI 脚本判定 `OK (21 files, no bytecode)` |
| 修 `pyproject.toml` 的 `package-data` | wheel 现含 `detector_config/detector.yaml`，干净安装实测 `yaml installed: ['detector.yaml']` |
| 新增 `tests/test_package_data.py` | 5 条测试；在坏 wheel 上**确认为失败**，修复后通过 |
| 全量测试 | **429 passed / 3 skipped** |
| 重新构建 dist | `tmaudit-0.6.0` 双包重建 |
| 分析文档 | 本文件 + `UPLOAD.md` |

**未做**：git commit、git merge、git push、任何 PyPI/TestPyPI 上传。
