# Prompt-coverage audit — i18n-mandarin-gap-coverage

This artefact discharges Requirement 6 of `i18n-mandarin-gap-coverage`. It
enumerates every Han-character literal currently present in the three
prompt-generator source files and classifies each as **covered** (already
tracked by the originating spec's `tasks.md`), **deliberately preserved**
(explicitly listed in the originating spec under a "Confirm … unchanged"
clause), or **uncovered** (no task in the originating spec references it).

Source data captured with
`rg --line-number --no-heading -nP '[\p{Han}]' backend/app/services/{oasis_profile_generator,ontology_generator,simulation_config_generator}.py`
on 2026-05-12.

This audit does **not** modify the three generator source files — Gap 1
of the umbrella issue is explicitly restricted to `zep_tools.py`,
`zep_graph_memory_updater.py`, and the four backend scripts. The audit's
purpose is to feed any **uncovered** strings back to the originating
specs' `tasks.md` so they are closed under the i18n initiative's existing
ownership boundaries.

## i18n-oasis-profile-generator-prompts

Source file: `backend/app/services/oasis_profile_generator.py`

| Line | Literal | Classification | Spec reference |
|---:|---|---|---|
| 67 | `# OASIS 库要求字段名为 username（无下划线）` | **Deliberately preserved** | `tasks.md:70` — "Confirm the module/class/method docstrings and inline comments are unchanged (including lines 65, 93, …)" |
| 94 | `# OASIS 库要求字段名为 username（无下划线）` | **Deliberately preserved** | same as line 67 |
| 193 | `raise ValueError("LLM_API_KEY 未配置")` | **Deliberately preserved** | `tasks.md:73` — "Confirm the `ValueError(\"LLM_API_KEY 未配置\")` raise at line 194 is unchanged" |
| 796 | `# 机构虚拟年龄` | **Deliberately preserved** | `tasks.md:70` — comments at "804–807, 816–819" listed as unchanged |
| 797 | `# 机构使用other` | **Deliberately preserved** | same |
| 798 | `# 机构风格：严谨保守` | **Deliberately preserved** | same |
| 799 | `"country": "中国",` | **Deliberately preserved** | `tasks.md:72` — "Confirm the rule-based `country: \"中国\"` default at lines 807, 819 is unchanged" |
| 808 | `# 机构虚拟年龄` | **Deliberately preserved** | same as 796 |
| 809 | `# 机构使用other` | **Deliberately preserved** | same |
| 810 | `# 机构风格：严谨保守` | **Deliberately preserved** | same |
| 811 | `"country": "中国",` | **Deliberately preserved** | `tasks.md:72` (paired entry for lines 807/819) |
| 1112 | `"男": "male",` (mapping key) | **Deliberately preserved** | `tasks.md:71` — "Confirm `_normalize_gender` mapping table (Chinese keys `男`/`女`/`机构`/`其他`) is unchanged" |
| 1113 | `"女": "female",` | **Deliberately preserved** | same |
| 1114 | `"机构": "other",` | **Deliberately preserved** | same |
| 1115 | `"其他": "other",` | **Deliberately preserved** | same |
| 1158 | `profile.country if profile.country else "中国"` | **Deliberately preserved** | `tasks.md:72` (same rationale as 799/811) |

**Result for this spec**: 0 uncovered, 16 deliberately preserved. No
follow-up tasks needed in `i18n-oasis-profile-generator-prompts`.

## i18n-ontology-generator-prompts

Source file: `backend/app/services/ontology_generator.py`

| Line | Literal | Classification | Spec reference |
|---:|---|---|---|
| 409 | `'自定义实体类型定义',` | **Uncovered** | not referenced in `tasks.md`; used as a docstring header inside `generate_python_code` output |
| 410 | `'由MiroFish自动生成，用于社会舆论模拟',` | **Uncovered** | same |
| 417 | `'# ============== 实体类型定义 =============='` | **Uncovered** | section header emitted into the generated Python code |
| 444 | `'# ============== 关系类型定义 =============='` | **Uncovered** | same |
| 473 | `'# ============== 类型配置 =============='` | **Uncovered** | same |

**Result for this spec**: 5 uncovered. These literals are emitted by
`generate_python_code` into a Python source file that downstream tooling
consumes. They are operator/developer-facing artefacts rather than LLM
prompts, which is why the prompt-focused spec did not cover them. A
follow-up task is appended to
`.kiro/specs/i18n-ontology-generator-prompts/tasks.md`.

## i18n-simulation-config-generator-prompts

Source file: `backend/app/services/simulation_config_generator.py`

| Line | Literal | Classification | Spec reference |
|---:|---|---|---|
| 240 | `raise ValueError("LLM_API_KEY 未配置")` | **Uncovered** | not referenced in `tasks.md`; module-level error message |
| 484 | `raise last_error or Exception("LLM调用失败")` | **Uncovered** | same |

**Result for this spec**: 2 uncovered. Both are Python exception messages
unrelated to the LLM prompt content the spec targets. A follow-up task is
appended to
`.kiro/specs/i18n-simulation-config-generator-prompts/tasks.md`.

## Aggregate

| Spec | Total Han hits | Covered | Deliberately preserved | Uncovered |
|---|---:|---:|---:|---:|
| `i18n-oasis-profile-generator-prompts` | 16 | 0 | 16 | 0 |
| `i18n-ontology-generator-prompts` | 5 | 0 | 0 | 5 |
| `i18n-simulation-config-generator-prompts` | 2 | 0 | 0 | 2 |

The two prompt specs without comprehensive coverage receive follow-up
tasks; the oasis spec is complete (every residual Han literal is
deliberately preserved by an explicit unchanged-clause).
