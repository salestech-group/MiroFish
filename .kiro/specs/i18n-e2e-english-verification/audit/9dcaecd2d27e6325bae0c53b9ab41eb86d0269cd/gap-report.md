# Verification gap report - i18n-e2e-english-verification

**Commit:** `9dcaecd2d27e6325bae0c53b9ab41eb86d0269cd`


## Overview

- Total CJK matches audited: **2916**
- Class distribution: deliberate=2299, review-needed=380, gap=237
- Gap categories: backend-prompt-label=143, frontend-ui-string=49, frontend-regex-parser=36, backend-log=9
- Gap pipeline steps: Report=70, Env Setup=61, n/a=47, UI=29, Simulation=14, Logs=9, Graph Build=5, Interaction=2

## Section 1 - Static CJK audit

Canonical command (PCRE):

```
git grep -nIP "[\x{4e00}-\x{9fff}]" -- backend/app frontend/src locales/en.json
```

Raw output captured at `audit/9dcaecd2d27e6325bae0c53b9ab41eb86d0269cd/cjk-grep.txt` and bucketed at `audit/9dcaecd2d27e6325bae0c53b9ab41eb86d0269cd/cjk-grep-bucketed.txt`.

`locales/en.json` CJK matches: **0** (acceptance: zero).

Top files by gap count:

| File | Gap count |
|------|-----------|
| `backend/app/services/oasis_profile_generator.py` | 60 |
| `frontend/src/components/Step4Report.vue` | 50 |
| `backend/app/services/zep_graph_memory_updater.py` | 47 |
| `frontend/src/views/Process.vue` | 29 |
| `backend/app/services/report_agent.py` | 20 |
| `backend/app/services/simulation_config_generator.py` | 13 |
| `backend/app/services/ontology_generator.py` | 5 |
| `backend/app/utils/retry.py` | 4 |
| `backend/app/api/graph.py` | 3 |
| `frontend/src/components/Step2EnvSetup.vue` | 3 |
| `frontend/src/components/Step5Interaction.vue` | 2 |
| `frontend/src/components/Step3Simulation.vue` | 1 |

## Section 2 - Locale catalogue parity

```
# Locale parity for HEAD
# en keys: 953
# zh keys: 953

[missing-keys]
# (none)

[cjk-in-en]
# (none)

[identical-values]
# (none)
```

## Section 3 - LLM-prompt locale verification

Backend prompt-label gaps (CJK string literals inside services that compose LLM prompts): **143**

First 10 examples (file:line - match):

- `backend/app/services/oasis_profile_generator.py:65` - "username": self.user_name,  # OASIS 库要求字段名为 username（无下划线）
- `backend/app/services/oasis_profile_generator.py:93` - "username": self.user_name,  # OASIS 库要求字段名为 username（无下划线）
- `backend/app/services/oasis_profile_generator.py:194` - raise ValueError("LLM_API_KEY 未配置")
- `backend/app/services/oasis_profile_generator.py:384` - all_summaries.add(f"相关实体: {node.name}")
- `backend/app/services/oasis_profile_generator.py:390` - context_parts.append("事实信息:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
- `backend/app/services/oasis_profile_generator.py:392` - context_parts.append("相关实体:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
- `backend/app/services/oasis_profile_generator.py:422` - context_parts.append("### 实体属性\n" + "\n".join(attrs))
- `backend/app/services/oasis_profile_generator.py:438` - relationships.append(f"- {entity.name} --[{edge_name}]--> (相关实体)")
- `backend/app/services/oasis_profile_generator.py:440` - relationships.append(f"- (相关实体) --[{edge_name}]--> {entity.name}")
- `backend/app/services/oasis_profile_generator.py:443` - context_parts.append("### 相关事实和关系\n" + "\n".join(relationships))
- ... and 133 more (see `classified.csv`)

These prompts feed the LLM verbatim; CJK labels bias the model toward Chinese output even when the requested locale is English.

## Section 4 - Locale propagation surface

| Boundary | Status | Evidence |
|----------|--------|----------|
| HTTP -> Flask handler | manual-pending | runtime not exercised in sandbox; static review showed no per-request locale carrier |
| Flask handler -> Task worker | manual-pending | thread-local `set_locale` referenced in CLAUDE.md but not statically verified end-to-end |
| Task worker -> OASIS subprocess | manual-pending | subprocess boundary requires live run |
| Backend logger | gap | 9 hard-coded CJK log line(s) on EN code path |

First 10 backend-log gap examples:

- `backend/app/api/graph.py:385` - build_logger.info(f"[{task_id}] 开始构建图谱...")
- `backend/app/api/graph.py:494` - build_logger.info(f"[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}")
- `backend/app/api/graph.py:513` - build_logger.error(f"[{task_id}] 图谱构建失败: {str(e)}")
- `backend/app/services/oasis_profile_generator.py:945` - print(f"开始生成Agent人设 - 共 {total} 个实体，并行数: {parallel_count}")
- `backend/app/services/oasis_profile_generator.py:1001` - print(f"人设生成完成！共生成 {len([p for p in profiles if p])} 个Agent")
- `backend/app/utils/retry.py:55` - logger.error(f"函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}")
- `backend/app/utils/retry.py:108` - logger.error(f"异步函数 {func.__name__} 在 {max_retries} 次重试后仍失败: {str(e)}")
- `backend/app/utils/retry.py:179` - logger.error(f"API调用在 {self.max_retries} 次重试后仍失败: {str(e)}")
- `backend/app/utils/retry.py:227` - logger.error(f"处理第 {idx + 1} 项失败: {str(e)}")

## Section 5 - Issue #10 checklist mapping

Each line below is taken from the ticket body, with an explicit status.

- [ ] **GAP** - **Frontend UI** — every label, button, modal, error toast, and tooltip in EN. No Chinese strings on screen. - 29 hard-coded CJK literal(s) in `frontend/src/views|components/`
- [ ] **GAP** - **Step 1 — Graph Build** - 5 gap(s) classified, see Section 1/3
  - MANUAL-PENDING: Status messages in EN - not verifiable statically; awaiting live run
  - GAP: Ontology JSON descriptions in EN (depends on #2) - 14 gap(s) classified, see Section 1/3
  - GAP: Backend logs in EN (depends on #6) - 9 gap(s) classified, see Section 1/3
- [ ] **GAP** - **Step 2 — Env Setup** - 61 gap(s) classified, see Section 1/3
  - GAP: Generated agent profiles (`bio`, `persona`, `profession`, `interested_topics`) in EN (depends on #3) - 61 gap(s) classified, see Section 1/3
  - MANUAL-PENDING: `gender` still the English enum (`male` / `female` / `other`) - not verifiable statically; awaiting live run
- [ ] **GAP** - **Step 3 — Simulation** - 14 gap(s) classified, see Section 1/3
  - GAP: Sim config `content`, `narrative_direction`, `hot_topics`, `reasoning` in EN (depends on #4) - 14 gap(s) classified, see Section 1/3
  - MANUAL-PENDING: `poster_type` still PascalCase English - not verifiable statically; awaiting live run
  - MANUAL-PENDING: `stance` still one of `supportive` / `opposing` / `neutral` / `observer` - not verifiable statically; awaiting live run
  - GAP: Generated tweets / Reddit posts in EN (depends on #3 personas + #4 sim config) - 14 gap(s) classified, see Section 1/3
- [ ] **GAP** - **Step 4 — Report** - 70 gap(s) classified, see Section 1/3
  - GAP: Report sections, headings, prose in EN (depends on #5) - 70 gap(s) classified, see Section 1/3
  - MANUAL-PENDING: ReACT thinking trace in EN - requires live walkthrough
  - MANUAL-PENDING: Tool-call results render correctly - requires live walkthrough
- [ ] **GAP** - **Step 5 — Interaction** - 2 gap(s) classified, see Section 1/3
  - GAP: Interview chat replies in EN (depends on #3) - 2 gap(s) classified, see Section 1/3
  - GAP: Report Agent chat replies in EN (depends on #5) - 72 gap(s) classified, see Section 1/3
- [ ] **GAP** - **Backend logs** — full pipeline-run logs in EN (depends on #6) - 9 gap(s) classified, see Section 1/3
- [ ] **GAP** - **Locale propagation** — confirm `Accept-Language: en` (or thread-local locale set via `set_locale`) reaches background tasks and survives the OASIS subprocess boundary. - 9 CJK log strings on EN code path
- [ ] **MANUAL-PENDING** - Every touchpoint above renders in Chinese; no English regressions. - requires live walkthrough
- [ ] **MANUAL-PENDING** - zh.json backfill (#8) covered: Step 3, Step 4, Step 5, and graph panel labels are all Chinese. - not verifiable statically; awaiting live run

## Section 6 - ZH regression check

- Locale catalogues at full key parity (953 EN keys / 953 ZH keys, symmetric difference 0 - see Section 2).
- No ZH-specific regression detected in static review. Live ZH walkthrough is `manual-pending`.

## Section 7 - Follow-up plan

Per R7.2, gaps are grouped into the following follow-up issues (placeholder bodies in `PENDING-followups/`):

1. **Frontend hard-coded UI strings** (49 matches + 36 regex parsers depending on CJK backend output).
2. **Backend log strings** (9 matches).
3. **Backend LLM-prompt context labels** (143 matches).
4. **Permanent CI guard** (preventative - re-run this audit on every PR).

Backend docstring/comment matches (the bulk of `deliberate` rows) are covered by the existing issue #7 and are not re-filed here.
