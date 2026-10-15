# Security Review: fullhouse-bot-e504793d480b1b975f25258d25939b45c6dbd5a4

## Scope

Offline static malware/security review of advitrocks9/fullhouse-bot upstream commit e504793d480b1b975f25258d25939b45c6dbd5a4. All Python source reviewed; no observed malware in fixed NPC runtime. Two vulnerabilities in optional vendored submission/match tooling.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: target_sha256_9f49538d95e1d08ac35ab8c4b0d48e46ceca1d15e55c6e09389e5416f3be19ec
- Revision: 92724c2c1039dae4a4d9f3fb21d68e8efbd76cc2
- Snapshot digest: codex-security-snapshot/v1:sha256:58f52425c8391a1cc70e7ae508d9c82411b55e7e38562bce9b2c2a440f10be63
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: Read-only offline static scan; target not executed.
- Artifacts reviewed: bot/bot.py, bot/features.py, bot/deep_cfr_lookup.py, data/deep_cfr_model.npz, data/preflop_equity.npz, requirements.txt, .github/workflows/ci.yml, engine_vendored/sandbox/validator.py, engine_vendored/sandbox/match.py
- Scan context: 其他金額也x5 然後檢查fullhouse-bot 裡面有沒有惡意程式

Limitations and exclusions:
- Static only: no target code, tests, training, installers or pickle/joblib loads executed during scan.
- 132 archive files inventoried; 131 received source or data-format review. Unused opponent_classifier.pkl only partially inspected; nested Joblib representation not fully decoded.
- External dependency distributions/native implementations, CI actions, base images and remote installers not audited. No certification of future revisions or installations.
- PNG review covered container structure/CRCs, not decoder security or hidden image content.
- Phone/Termux compatibility and poker-strength validation not performed.
- Workbench targetRevision is parent workspace 92724c2c1039dae4a4d9f3fb21d68e8efbd76cc2; audited upstream commit is e504793d480b1b975f25258d25939b45c6dbd5a4. Archive SHA256 772d2110c7e44675ee33d7fbcb0e605846e78532ecf8e511dd85be9a3d42d48a.
- Fresh architecture spawn hit thread cap, so a completed preflight worker performed architecture review. Independent fresh-context baseline and separate focused audit were available.
- Excluded external dependency distributions and services: Outside immutable repository; not downloaded or executed.

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 2 |
| Severity mix | medium: 1, low: 1 |
| Confidence mix | high: 2 |
| Coverage | partial |
| Validation mode | static-source-tracing |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

fullhouse-bot is a six-player poker inference bot, with separate training, benchmark, cluster and release tooling (README.md:19, README.md:77). Runtime decide(state) invokes NumPy Deep CFR inference (bot/bot.py:353, bot/bot.py:366). Packaging concatenates features.py, deep_cfr_lookup.py and bot.py and includes data/preflop_equity.npz plus deep_cfr_model\*.npz (tooling/release/submission.py:19, tooling/runtime_data.py:13). User context: intended use is only bot plus NPZ on Android; the Android host integration is unspecified.

### Assets

- Android host files, permissions and process authority: Python imports execute bot source directly; containment must come from the hosting application or OS (engine_vendored/sandbox/runner.py:31).
- Runtime model integrity and decision availability: BOT_DATA_DIR controls the directory supplying all matching model NPZs and preflop_equity.npz (bot/bot.py:39, bot/bot.py:73, bot/features.py:49, bot/features.py:65).
- Optional developer assets include checkpoint state, repository contents and existing SSH authority used by cluster synchronization (training/train.py:529, scripts/cluster_deploy.sh:16, tooling/watcher/sync.py:18).

### Trust Boundaries

- Source import to host execution: BOT_PATH defaults to /bot/bot.py and importlib executes its module; checking for decide happens afterward (engine_vendored/sandbox/runner.py:26, engine_vendored/sandbox/runner.py:31).
- Data files to numeric inference: BOT_DATA_DIR overrides a sibling data directory, falling back to the parent data directory; consumers load deep_cfr_model\*.npz and preflop_equity.npz with np.load, then access arrays (bot/features.py:40, bot/features.py:49, bot/features.py:65, bot/bot.py:73, bot/deep_cfr_lookup.py:38).
- Docker execution boundary: explicit USE_DOCKER=true enables network none, memory/CPU limits, read-only root, UID 1000, no-new-privileges and read-only /bot mount; /tmp is writable tmpfs (engine_vendored/sandbox/match.py:116). Local mode runs the same runner directly without these container controls (engine_vendored/sandbox/match.py:135).
- Game state to decision: runner parses stdin JSON and calls bot.decide on daemon threads with a wait timeout; timeout does not terminate an executing thread (engine_vendored/sandbox/runner.py:48, engine_vendored/sandbox/runner.py:63, engine_vendored/sandbox/runner.py:89, engine_vendored/sandbox/runner.py:103).
- Optional development boundaries: SSH/scp/rsync exchange checkpoints and repository files with configured hosts; training resume passes local latest.pt to torch.load(weights_only=False); cluster environment setup downloads an HTTPS installer and pipes it to sh (tooling/watcher/sync.py:18, scripts/cluster_deploy.sh:16, training/train.py:532, scripts/cluster_build_venv.sh:9).

### Attacker Capabilities

- A bot or model distributor can supply Python source or NPZ files the user elects to install. Malicious Python already receives the host interpreter's authority when imported; NPZ-only attacker control must be evaluated separately against NumPy parsing (engine_vendored/sandbox/runner.py:34, bot/deep_cfr_lookup.py:39).
- Game-state producers supply dictionaries through decide or newline JSON through the runner; no network listener is established by this interface (bot/bot.py:353, engine_vendored/sandbox/runner.py:84).
- Conditional training attacker: an actor able to replace the selected latest.pt can reach unrestricted PyTorch deserialization only when the operator enables resume (training/train.py:529, training/train.py:532). Do not assume this actor controls normal bot-only execution.

### Security Objectives

- For the user's Android deployment, establish that the exact bot and NPZ artifacts perform only requested inference and that host permissions limit unintended filesystem/network access; competition documentation alone cannot establish containment (README.md:72, engine_vendored/sandbox/match.py:116).
- Keep numeric model loading distinct from executable checkpoint deserialization, and require trusted provenance for optional latest.pt resume files (bot/deep_cfr_lookup.py:39, training/train.py:532).
- Preserve model/data selection integrity and maintain bounded decision/resource behavior for potentially malformed state or weights (bot/bot.py:73, bot/deep_cfr_lookup.py:32).

### Assumptions

- The README's no-network/read-only sandbox description concerns the competition environment (README.md:6, README.md:72). Local vendored execution defaults to USE_DOCKER=false and inherits the host environment (engine_vendored/sandbox/match.py:32, engine_vendored/sandbox/match.py:136, engine_vendored/sandbox/match.py:139). Android execution does not inherit those Docker guarantees automatically.
- Runtime NPZ loading does not request allow_pickle=True (bot/deep_cfr_lookup.py:39, bot/features.py:71). Installed NumPy/native dependency implementations and actual supplied NPZ contents were not inspected in this architecture pass.
- Training, cluster synchronization, installation and publication packaging are separate opt-in developer workflows; their operations are not evidence of runtime malware (README.md:99, scripts/cluster_deploy.sh:3).
- No source-backed Android wrapper, permission model or installed dependency versions were established. This is architecture mapping, not complete audit coverage.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [驗證外來 Bot 可在主機直接執行其程式](#finding-1) | medium | high | inline below |
| [外來 Bot 可讓比賽程序無限等待](#finding-2) | low | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] 驗證外來 Bot 可在主機直接執行其程式

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Independent source review confirms both bypassable checks and unsandboxed exec_module; no exploit was executed. |
| Category | code-injection |
| CWE | CWE-94, CWE-693 |
| Affected lines | engine_vendored/sandbox/validator.py:344-347, engine_vendored/sandbox/validator.py:523-534 |

#### Summary

可選的比賽驗證器以可繞過的 AST 黑名單檢查外來 bot.py，隨後直接在驗證程序匯入它。惡意提交者可藉由未被識別的匯入別名取得驗證主機使用者的程式執行權限；這不是固定主模型含有惡意程式的證據。

#### Root Cause

The CLI accepts an external bot path. check_static allows os imports and matches only specific names or literal os attributes, so an imported system alias is not rejected. validate then calls load_bot, whose exec_module executes submission code inside the host validator.

**Validation imports submitted source after static checks** — `engine_vendored/sandbox/validator.py:530-534`

After a submission passes the denylist, its resolved path is forwarded to the host importer.

```
        if results["errors"]:
            return results

        try:
            bot = load_bot(bot_py)
```

**Only selected direct call names are blocked** — `engine_vendored/sandbox/validator.py:258-260`

Calls via names imported from permitted os are not in the banned builtin list; os is explicitly allowed at lines 42-56.

```
    for node in ast.walk(tree):
        # Direct calls to banned builtins: __import__(...), eval(...), exec(...), compile(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALL_NAMES:
```

**Submission module executes in validator process** — `engine_vendored/sandbox/validator.py:344-347`

exec_module evaluates arbitrary top-level submission Python without an isolation boundary.

```
def load_bot(path: str):
    spec   = importlib.util.spec_from_file_location("bot_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
```

#### Validation

Source trace confirms a submission using a from-os import can pass the denylist and execute at module import. Docker controls exist only in the separate match launcher, not this validator. No target code or payload was executed.

Validation method: static

#### Dataflow

CLI bot_path -\> _resolve_submission -\> check_static -\> load_bot -\> spec.loader.exec_module.

#### Reachability

Reachable through validator CLI/validate API when used on another party's submission. Fixed bundled model-only integration does not require this path.

#### Severity

**Medium** — Host code execution has high impact, but requires an operator to run the optional local validator on an attacker-supplied submission; no remote submission endpoint is present.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Run all import-time and decision-time validation in a separate restricted process/container without host credentials or writable host mounts. Treat AST checks as lint, not isolation.

<a id="finding-2"></a>

### [2] 外來 Bot 可讓比賽程序無限等待

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | The parent readline has no deadline and child module import precedes the timeout; source path independently confirmed. |
| Category | denial-of-service |
| CWE | CWE-400, CWE-835 |
| Affected lines | engine_vendored/sandbox/match.py:184-187, engine_vendored/sandbox/match.py:158-161, engine_vendored/sandbox/runner.py:74-76 |

#### Summary

可選的比賽工具在主機端無期限等待 Bot 的啟動與動作回覆。Bot 匯入發生於計時控制之前，因此惡意提交可在匯入階段卡住比賽，即使啟用 Docker 仍然如此。

#### Root Cause

run_match warms each subprocess before its cleanup try/finally. warmup and act block on stdout.readline without an external deadline. The child imports bot source before starting the timed decision loop, so import-time nontermination never reaches the timer.

**Parent warmup waits without a deadline** — `engine_vendored/sandbox/match.py:184-187`

If the child remains alive but produces no newline, the parent cannot advance or reach cleanup.

```
        try:
            self._proc.stdin.write(json.dumps({"type": "warmup"}) + "\n")
            self._proc.stdin.flush()
            self._proc.stdout.readline()  # discard
```

**Child imports bot before timed decisions** — `engine_vendored/sandbox/runner.py:74-76`

Attacker-controlled module import happens before the timeout call at line 103, outside its enforcement.

```
def main():
    try:
        bot = load_bot(BOT_PATH)
```

#### Validation

Reviewed parent and child control flow: no deadline surrounds parent I/O; Docker only constrains CPU/memory/network and does not set a runtime limit. Ordinary decide timeouts do not cover import. No hanging payload was run.

Validation method: static

#### Dataflow

bot_paths -\> BotProcess -\> runner.load_bot -\> import-time nontermination -\> parent warmup stdout.readline.

#### Reachability

Optional run_match/CLI accept bot paths; default local mode and Docker mode both share the unbounded parent wait. Fixed main model has no observed malicious trigger.

#### Severity

**Low** — Availability impact is limited to optional local tournament jobs, requires running an attacker-supplied bot, and does not establish remote exposure or container escape.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Enforce host-side startup and per-response deadlines, bounded output and drained stderr, and kill/reap the owned process or container on timeout. Cover startup and warmup with cleanup finally.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Fixed NPC runtime and main NPZ model | not recorded | No issue found | No additional canonical notes were recorded. |
| Independent baseline: runtime, opponents, packaging and tooling | not recorded | No issue found | No additional canonical notes were recorded. |
| Training and watcher source | not recorded | No issue found | No additional canonical notes were recorded. |
| Optional submission validation and match execution | not recorded | Reported | No additional canonical notes were recorded. |
| Five vendored example bots | not recorded | No issue found | No additional canonical notes were recorded. |
| Documentation, initializers and metadata | not recorded | No issue found | No additional canonical notes were recorded. |
| JSON and 18 numerical NPY/NPZ artifacts | not recorded | No issue found | No additional canonical notes were recorded. |
| Two documentation PNG files | not recorded | No issue found | No additional canonical notes were recorded. |
| Unused opponent_classifier.pkl | not recorded | Needs follow-up | No additional canonical notes were recorded. |
| Additional parent-reviewed engine and tooling | not recorded | No issue found | No additional canonical notes were recorded. |
| Tests and optional sandbox | not recorded | Reported | No additional canonical notes were recorded. |
| Training and watcher full source audit | not recorded | No issue found | No additional canonical notes were recorded. |
| Three runtime modules and numeric model data | not recorded | No issue found | No additional canonical notes were recorded. |
| Independent baseline interim result | not recorded | No issue found | No additional canonical notes were recorded. |

## Open Questions And Follow Up

- Future Android integration must provide host permissions and startup deadlines; no deployed Discord integration exists in this target to audit.
- Nested Joblib representation not fully decoded. Opcode prefix and strings reviewed; no source consumer and not included in main runtime package.
  - Follow-up prompt: Review deferred unit deferred-2caab795eee3f3ce and close its stated proof gap.
- Nested Joblib contents not completely decoded; no runtime consumer, prefix and strings only.
  - Follow-up prompt: Review deferred unit deferred-87a7ad4d4289be74 and close its stated proof gap.
- Final documentation and data static checks.
  - Follow-up prompt: Review deferred unit deferred-00401c5e8978d8a7 and close its stated proof gap.
- Final inventory reconciliation and vendored bots still in progress.
  - Follow-up prompt: Review deferred unit deferred-2c056fbb6d8ef8ea and close its stated proof gap.
- Remaining source groups still under review.
  - Follow-up prompt: Review deferred unit deferred-217ff6e994e0a27a and close its stated proof gap.
- Remaining source groups still undergoing full review.
  - Follow-up prompt: Review deferred unit deferred-ec22cb4ee6144d24 and close its stated proof gap.
- Independent full source audit in progress
  - Follow-up prompt: Review deferred unit baseline and close its stated proof gap.
- Independent investigation of validator host execution and match I/O blocking in progress
  - Follow-up prompt: Review deferred unit sandbox and close its stated proof gap.
- Joblib classifier contains embedded pickle; prefix statically disassembled, remainder not yet fully parsed. No source consumer found.
  - Follow-up prompt: Review deferred unit classifier and close its stated proof gap.
