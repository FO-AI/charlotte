# Outside scholarships pipeline speed (issue #17)

**Issue:** [#17 — Pipeline runs input-to-output in a fraction of today's time, with redundant stages removed](https://github.com/FO-AI/charlotte/issues/17)  
**Status:** Plan (measurement not yet committed)  
**Base:** `main` after #55 (supporting pages) and #56 (per-PID amount splits)  
**Related (out of scope for this clock):** [#18](https://github.com/FO-AI/charlotte/issues/18) Payment Validation VLOOKUP (Excel export only) · [#58](https://github.com/FO-AI/charlotte/issues/58) / [impact quantification doc](./outside-scholarships-impact-quantification-issue-58.md) (time → $ for leadership; separate from wall-clock speed)

---

## Goal (from #17)

The pipeline is too slow from input to output. Before optimizing:

1. Measure each stage on a representative batch and record a baseline.
2. Remove stages that add no information to the output.
3. Collapse sequential work that can run in parallel.

**Done when**

- [ ] A per-stage timing breakdown is committed (script or log format), run against a representative batch, with the baseline recorded on the issue.
- [ ] Every stage kept in the pipeline has a one-line justification; anything without one is removed.
- [ ] End-to-end time on the same batch is reduced against the baseline, with the after number recorded on the issue.
- [ ] Output is unchanged on the test batch (diff results before and after).

---

## What “input → output” means

Use **upload → preview-ready JSON** as the #17 clock.

| Endpoint | Role for #17 |
| --- | --- |
| `POST /api/banking/outside-scholarships` | Critical path — returns review preview; this is “output” |
| `POST /api/banking/outside-scholarships/export` | Secondary — after human review; do not optimize under #17 unless stakeholders redefine the clock |

Excel export is a separate route and overlaps with #18. Keep #17 focused on preview latency so export-column work does not block speed work.

---

## Pipeline map

```
PDF upload
  → validate / read bytes
  → classify pages (50 DPI thumbs, batches of 10, vision LLM)
  → force page 1 = front; group front / back / supporting
  → fan-out one worker per check (max concurrency 16)
       → render extraction PNGs (200 DPI) + preview JPEGs (150 DPI)
       → vision extract (front + back + all supporting pages)
  → aggregate (restore check order)
  → Active Directory lookup (distinct PIDs)
  → preview JSON (base64 images + fields)
```

Constants (today):

| Knob | Value | Where |
| --- | --- | --- |
| `MAX_CONCURRENT_CHECKS` | 16 | `backend/services/banking/outside_scholarships/service.py` |
| Side classification DPI | 50 | `nodes.py` |
| Classification batch size | 10 pages | `nodes.py` |
| Extraction PNG DPI | 200 | `nodes.py` |
| Preview JPEG DPI / quality | 150 / 75 | `nodes.py` |
| PyMuPDF | Global lock (not thread-safe) | `nodes.py` |

---

## Stage inventory

| Stage | What it does | Keep? | One-line justification | Likely time |
| --- | --- | --- | --- | --- |
| Upload validation / read | One PDF, type/size, read bytes | Keep | Required ingress and size guard | L |
| Side thumbnail render | 50 DPI PNGs for classification | Keep (measure) | Needed unless a non-LLM classifier replaces it | M |
| Side classification LLM | Label front / back / supporting | Keep | Grouping (and #55/#56) depends on correct sides | M–H |
| Group pages | Attach backs/supporting to checks | Keep | Preserves page ownership for extract and review | L |
| Per-check PDF split | Build `pair_pdf_bytes` per check | **Remove candidate** | Adds no user-visible info if workers can render original page indexes | M |
| Per-check render | 200 DPI extract + 150 DPI preview | Keep; **defer preview** | Extraction needs PNGs; preview JPEGs are not sent to the model | M |
| Vision extraction | One LLM call per check (+ supporting) | Keep | Cashier-visible fields come from here | H |
| Normalize fields | PIDs, amounts, terms, split cleanup | Keep | Protects review/export correctness | L |
| Aggregate | Restore check order after fan-out | Keep | Concurrency would otherwise scramble rows | L |
| AD lookup | Graph names for distinct PIDs | Keep | Preview mismatch / display; measure separately | L–M |
| Preview JSON build | Review payload + images | Keep | This *is* the #17 output | L–M (payload) |
| Excel export | Workbook after review | Out of #17 clock | Separate route; #18 territory | — |

---

## Measurement gap vs Done-when

### What exists

| Asset | Gap |
| --- | --- |
| `backend/tests/test_outside_scholarships_benchmark.py` | Fake LLM sleeps; reports gitignored; labels timing `upload_to_excel` though it only hits preview |
| `backend/tests/test_outside_scholarships_real_pdf.py` | Real PDF total runtime + field diffs; **no per-stage timings** |
| Service / node logs | Anchors exist; not a committed stage breakdown |

### What to commit for #17

1. **Stage-timing harness / report format** with fields such as:
   - `commit`, `label`, `pages`, `checks`, `supporting_pages`, `max_concurrency`
   - DPI constants, call counts, peak in-flight
   - `preview_json_bytes` / `preview_image_chars`
   - per-stage `{ first_start, last_end, wall_seconds, calls }` for: classify, group/split, render, extract, AD, preview serialize
2. **Stage justification** — this document (or a short sibling next to the harness).
3. **Baseline on the issue** — paste redacted numbers into #17 after the first real run.
4. **Diff harness** — semantic compare of preview fields before/after; image presence/hashes if claiming image identity.

### Representative batch

Primary: Derek combined PDF  
`10132026 Scholarship Check Images with Supporting Documentation 1382444.pdf` (~44 pages, supporting docs). Supporting pages are on the hot path after #55/#56; synthetic 50-check-only batches understate cost.

| Run | Intent |
| --- | --- |
| Real baseline / after | Opt-in real PDF eval with `issue17-before` / `issue17-after` labels + baseline diff |
| Synthetic guard | Existing benchmark for CPU / render / concurrency regressions — not the authority for #17 numbers |

---

## Speedup backlog (only after baseline)

| Pri | Change | Why “output unchanged” is plausible | Expected win | Risk |
| --- | --- | --- | --- | --- |
| P0 | Commit stage timings; fix benchmark label to preview | No behavior change | Unblocks #17 | None |
| P0 | Defer preview JPEG render until after extract call | Same images, later in the critical section | M | Render still contended under PyMuPDF lock |
| P0 | Remove per-check PDF split; render from source page indexes | Same pages if pixels match | M | Pixel / lock / memory differences |
| P1 | Tune `MAX_CONCURRENT_CHECKS` from Azure quota (env-configurable) | Scheduling only; order tests already exist | H if waves dominate | 429s, cost |
| P1 | Larger classify batches **only if** classify is hot in logs | Fewer LLM calls, same labels | L–M | Token/image limits |
| P1 | Overlap AD with preview assembly if AD is slow | Same Graph results | L–M | Failure handling |
| P2 | Lower extract/preview DPI | Not byte-identical; needs owner OK | M–H | Extraction quality |
| P2 | Heuristic skip of supporting pages | Unsafe under #55/#56/#34 | — | Missed terms/splits |

**Do not do under #17:** load PaymentValidation.xlsx on the server (#18 forbids that); strip supporting pages; remove AD from preview without a product decision.

---

## Removable / collapsible stages

| Candidate | Action |
| --- | --- |
| Per-check PDF materialization (`pair_pdf_bytes`) | Remove if render-from-indexes matches images + fields on Derek batch |
| Preview JPEG render before extract | Defer out of pre-LLM critical section if render shows up in timings |

**Not safely removable:** supporting pages, side classification, extraction, normalization, AD for preview, aggregate ordering.

---

## Recommended PR sequence

1. **Measurement only** — stage timing report format, correct preview clock naming, link this doc, run Derek baseline, paste numbers on #17.
2. **Diff harness** — page metadata, supporting flags, PID amount rows, image hash policy.
3. **Low-risk render cleanup** — defer preview JPEGs and/or drop per-check PDF split; merge only if Derek diff is clean.
4. **Concurrency tuning** — from measured quota / retry data.
5. **Heavier changes (optional)** — DPI / classifier only if non-byte-identical images are accepted and semantic diff stays clean.

---

## Realistic expectation

The graph already parallelizes classification batches and per-check extraction. Counting that again is not a win.

| If baseline shows… | Plausible preview time vs today |
| --- | --- |
| Render / split / concurrency waves are hot | ~50–70% of current |
| Azure vision already fully overlapped and rate-limited | ~80–90% of current |

“A fraction of today’s time” is the issue title’s ambition; treat **measured preview wall time on the Derek batch** as the scoreboard, not synthetic fake-LLM numbers.

---

## Immediate next actions

1. Implement committed per-stage timing (PR 1).
2. Run Derek PDF baseline; comment numbers on [#17](https://github.com/FO-AI/charlotte/issues/17).
3. Only then land defer-preview / drop-split with a before/after diff.

---

## Key code pointers

| Area | Path |
| --- | --- |
| Graph fan-out | `backend/services/banking/outside_scholarships/graph.py` |
| Classify / group / render / extract | `backend/services/banking/outside_scholarships/nodes.py` |
| Upload + preview + concurrency cap | `backend/services/banking/outside_scholarships/service.py` |
| AD lookup | `backend/services/banking/outside_scholarships/active_directory_names.py` |
| Opt-in fake benchmark | `backend/tests/test_outside_scholarships_benchmark.py` |
| Real PDF eval | `backend/tests/test_outside_scholarships_real_pdf.py` |
| Upload route | `backend/api/routes/banking.py` |
