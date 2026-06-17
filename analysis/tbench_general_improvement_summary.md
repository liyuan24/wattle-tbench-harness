# Terminal-Bench 2.0 General Wattle Improvement Summary

Generated from the GCP amd64 Wattle run `wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616`.

Snapshot used: `2026-06-17T10:26:11Z`

This summary intentionally avoids task-specific fixes. It ranks general Wattle improvements by expected pass-rate impact, breadth across failures, and implementation practicality.

## Priority 1: Add Final-State Contract Validation

Wattle frequently did useful work but failed because the final verifier-visible state was wrong.

Observed in:

- `polyglot-c-py`: correct source, extra `cmain`; Codex also failed the comparison with the same leftover artifact.
- `polyglot-rust-c`: correct source, extra `main` and `cmain` across three Wattle attempts; Codex also failed the comparison by leaving an extra `main`, so exact final inventory is a broad failure mode.
- `configure-git-webserver`: smoke-tested successfully, then reset state so verifier saw 404; Codex also failed the comparison with HTTP 404, and a Wattle retry with a deployment hook/server still failed with HTTP 000.
- `qemu-startup`: one Wattle attempt passed, but a retry timed out with the VM no longer running and required side artifacts missing, showing service liveness must be checked at final handoff.
- `financial-document-processor`: two Wattle attempts moved a partial set of files and left `summary.csv` missing.
- `build-pov-ray`: the first Wattle attempt built a working executable but missed source/provenance artifacts; a retry passed after preserving official 2.2 archives/layout, and Codex also passed the comparison.
- `mcmc-sampling-stan`: plausible posterior mean files were produced, then later experimentation left bad verifier-visible outputs; a retry passed after preserving the pinned RStan sampling path and final means.
- `sam-cell-seg`: one attempt's segmentation geometry was accepted, but the serialized CSV coordinate fields used tuple syntax instead of verifier-accepted flat lists.
- `winning-avg-corewars`: a retry timed out and left an early placeholder/test warrior as the verifier-visible final file, even though no fully passing candidate had been validated.
- `extract-moves-from-video`: retry's last logged tool wrote `/app/solution.txt`, but after timeout the verifier saw no such file, so final artifact persistence was not guaranteed.

General fix:

- Before final response, Wattle should run a lightweight "final state audit" derived from the task instruction:
  - required files exist
  - forbidden extra files are absent when directory contents are constrained
- services/ports/processes are still alive
- required service side artifacts still exist
  - output paths match exactly
  - serialized output fields have the expected concrete types
  - validation artifacts are removed or written outside checked directories
- The audit should be a separate final tool phase, not just natural-language confidence.

## Priority 2: Infer And Reproduce Verifier-Like Checks

Several failures passed Wattle's own smoke tests but not the real verifier. The issue was not lack of effort; it was validating the wrong contract.

Observed in:

- `mteb-retrieve`: wrong MTEB wrapper/prompt semantics produced the wrong ranked document; Codex passed the same task, reinforcing that exact API parity is achievable in the harness.
- `mteb-leaderboard`: two Wattle attempts repeated the same wrong leaderboard answer; Codex passed the comparison, so exact snapshot/completeness/aggregation reproduction is feasible in the same environment.
- `train-fasttext`: two Wattle attempts and Codex all failed below the private verifier threshold, so exact data conversion/training settings and validation margin matter broadly.
- `gpt2-codegolf`: implementation did not satisfy exact compile/path/CLI/output contract across two Wattle attempts; Codex passed the same task, which points to Wattle's exact validation loop rather than an environment issue.
- `make-mips-interpreter`: one Wattle attempt passed, but a retry accepted a booting Doom run and valid BMP container while missing exact graphics-init stdout and the required frame-similarity threshold.
- `torch-tensor-parallelism`: forward/syntax checks missed backward distributed gradient mismatch.
- `pytorch-model-recovery`: TorchScript model saved with the wrong `forward(src, tgt)` interface, despite plausible model-recovery work.
- `overfull-hbox`: failed attempts had no overfull boxes but used invalid substitutions; a Wattle retry passed after preserving the allowed edit set, while Codex still failed the comparison with the same contract miss.
- `filter-js-from-html`: two Wattle attempts and Codex missed XSS vectors and modified clean files, showing sanitizer tasks need paired adversarial and clean-preservation regression checks.
- `sam-cell-seg`: one attempt passed substantive image-mask checks but failed exact serialized coordinate type; a retry still failed that schema check and also missed a mask-alignment IoU threshold.
- `model-extraction-relu-logits`: one failed attempt validated against visible model internals, but hidden verifier weights exposed incomplete recovery; a retry passed after improving the query-based recovery path.
- `dna-insert`: repeated attempts reported matching primer Tm values locally, but the verifier reconstructed the primer pair in a different orientation and found the Tm delta above threshold.
- `dna-assembly`: repeated local validation reported primer-pair Tm differences within threshold, but the verifier still found above-threshold deltas against the 5 C limit.

General fix:

- Wattle should convert the task prompt into an explicit validation checklist with both positive and negative assertions.
- When `/tests` is visible or can be copied, Wattle should inspect tests early and run the same pytest/script path after each candidate fix.
- When tests are unavailable, Wattle should synthesize verifier-like checks from:
  - exact output filenames
  - allowed edit set
  - command-line interface
  - size limits
  - private-input format
  - serialized file schema and field types after reloading from disk
  - hidden/private variants of visible examples when the prompt implies generality
  - multi-rank/backward/edge-case behavior
  - model/service function signatures
- Final "done" should require those checks to pass, or explicitly state the unmet risk.

## Priority 3: Preserve Oracle/API Semantics For External Benchmarks And Libraries

Benchmark/library tasks failed when Wattle approximated an API instead of matching exact semantics.

Observed in:

- `mteb-retrieve`: `mteb.get_model`, model revision, `SciFact`, query/passage prompt types, and fifth-highest ranking all mattered; Codex passing this comparison points to Wattle's semantic reproduction rather than an environment limitation.
- `mteb-leaderboard`: results repo commit, benchmark name, full-task filtering, and averaging mattered; two Wattle attempts picked the same plausible-but-wrong model while Codex passed, pointing to Wattle's semantic reproduction rather than a task/harness limitation.
- `raman-fitting`: unit conversion and crop ranges mattered before fitting; two Wattle attempts and Codex all fit wrong peaks, so the improvement should enforce scientific preprocessing and window selection explicitly.
- `db-wal-recovery`: SQLite WAL semantics and XOR decryption mattered before JSON extraction; Codex passed the comparison, so this is a Wattle semantic-fidelity miss rather than an apparent task/harness issue.
- `mcmc-sampling-stan`: prior parameterization and final posterior files mattered, not just script/file existence; a retry passed by keeping the requested RStan sampling path and posterior artifacts stable.

General fix:

- Add a "semantic fidelity" mode for tasks mentioning named libraries, benchmarks, file formats, scientific procedures, or model wrappers.
- In this mode Wattle should:
  - inspect installed package API docs/source when local
  - pin revision/version paths from the prompt
  - preserve named task/mode/prompt-type parameters exactly
  - avoid substituting a raw implementation for a wrapper unless it proves equivalence
  - validate intermediate semantics, not only final files

## Priority 4: Make Time-Budget Planning More Aggressive For Long Build/Training Tasks

Timeouts and partial long-running work are a recurring failure class.

Observed in:

- `caffe-cifar-10`: build/train did not finish required artifacts.
- `make-doom-for-mips`: two Wattle attempts and Codex all timed out after partial Doom/VM progress without reaching the expected graphics initialization and reference-like frame.
- `install-windows-3.11`: first Wattle attempt did not leave services running; retry fixed liveness/path but still failed visual feedback, while Codex also failed path/visual-feedback checks.
- `train-fasttext`: both Wattle attempts timed out and still missed accuracy; Codex also completed below threshold, which keeps the lesson focused on fast oracle-like training paths plus verifier-matched validation rather than Wattle-only timeout handling.
- `mcmc-sampling-stan`: long sampling and late reruns consumed budget and left bad final artifacts, while the retry passed by avoiding late artifact-damaging experimentation.

General fix:

- At task start, classify whether the task is build-heavy, training-heavy, emulator-heavy, or service-heavy.
- For those classes, Wattle should:
  - plan with hard checkpoints at 25%, 50%, and 75% of remaining time
  - prefer oracle-like minimal paths over exploratory rewrites
  - continuously verify artifact existence after each expensive phase
  - switch to fallback/minimal-completion mode when remaining time is low
  - avoid spending late budget on broad debugging unless the required final artifacts already exist

## Priority 5: Add Cleanup-Aware Validation Harnesses

Wattle often created temporary files in the same directories the verifier checked.

Observed in:

- `polyglot-c-py`
- `polyglot-rust-c`: Wattle and Codex both left compiled artifacts in the verifier-checked directory.
- likely other compile/smoke-test tasks where artifacts were harmless to humans but harmful to exact tests

General fix:

- Validation commands should default to temporary output directories or `/tmp`.
- When validating inside target directories is necessary, Wattle should record generated paths and clean them before final response.
- Wattle should run a post-cleanup validation that checks the deliverable still works without extra files.

## Priority 6: Improve Data/Media Extraction Confidence

Some failures came from accepting plausible extracted content too early.

Observed in:

- `gcode-to-text`: two Wattle attempts failed; the first decoded a plausible sentence, while the retry produced a near-flag string with exact-character errors. Codex passed the comparison, so stronger rendering/OCR and character-level validation are feasible under the same environment.
- `extract-moves-from-video`: one attempt had low command-sequence similarity, and the retry timed out with the verifier seeing no final `solution.txt`; Codex passed the comparison, so a stronger extraction workflow plus final artifact persistence is feasible under the same task/harness.
- `video-processing`: two Wattle attempts and Codex all failed tight frame-boundary checks, so the issue is exact temporal calibration rather than only one implementation's heuristic.
- `sam-cell-seg`: retry missed a mask-alignment IoU threshold while also failing serialized-coordinate schema, showing image-mask tasks need both geometry scoring and output-format validation.
- `financial-document-processor`: repeated manual/partial classification did not complete all files or `summary.csv`; Codex passed the comparison, so transaction-style staging and coverage validation are feasible.

General fix:

- For OCR, video, and media tasks, Wattle should run multiple extraction strategies and compare results.
- It should require confidence signals tied to the task:
  - expected flag/pattern format
  - line count or edit-distance similarity
  - frame boundary tolerance
  - total input-file coverage
  - classification totals
- If outputs are near-boundary, Wattle should explicitly test adjacent candidates.

## Priority 7: Strengthen Domain-Specific Semantic Checks

Several outputs were syntactically valid but semantically wrong.

Observed in:

- `protein-assembly`: two Wattle attempts produced valid-looking DNA and locally claimed correct component order, but the verifier still found the protein order wrong; Codex passed, so verifier-equivalent component grounding/order validation is feasible under the same task/harness.
- `extract-elf`: initial JSON was valid but ELF memory/symbol content was wrong; a Wattle retry passed after addressing parser/address-convention semantics, while Codex had also failed with 0% expected values.
- `raman-fitting`: JSON valid, scientific fit wrong across two Wattle attempts and Codex; repeated convergence to wrong peak centers reinforces that generic curve fitting without verified unit conversion and domain windows is insufficient.
- `torch-tensor-parallelism`: module valid, distributed gradients wrong.
- `pytorch-model-recovery`: model artifact valid enough to save, but not callable through the verifier's expected interface.
- `model-extraction-relu-logits`: one failed attempt recovered rows that matched visible weights but not the verifier's hidden generated matrix; the later pass keeps the lesson focused on hidden-shape/seed robustness.
- `dna-insert`: repeated primer sequences were syntactically valid and encoded the insert, but the annealing-arm orientation and Tm contract were not verifier-equivalent.
- `dna-assembly`: primer inventory and assembly intent were plausible across attempts, but the exact Golden Gate reconstruction and annealing Tm margin still failed.

General fix:

- Wattle should identify domain objects in the prompt and create intermediate semantic assertions:
  - translated protein contains components in required order
  - ELF sections and symbol tables are represented
  - scientific units/ranges are correct before optimization
  - sequence orientation and reverse-complement conventions match the verifier's reconstruction path
  - distributed gradients match a non-parallel reference
  - model-extraction outputs generalize across random seeds and hidden widths
- These checks should be run before declaring completion.

## Priority 8: Keep Prompt Caching Healthy But Do Not Optimize It Blindly

The current run's aggregate prompt-cache hit rate is 85.0%, which is much better than the earlier 49.2% signal. The cache issue no longer appears to be the dominant cause of failures in this snapshot.

General fix:

- Keep the current prompt-cache improvements.
- Continue reporting cache hit rate per run and per trial.
- Flag trials below a cache threshold only as a cost/performance issue unless logs show context instability also caused behavioral regressions.

## Suggested Implementation Order

1. Final-state contract audit.
2. Verifier-like validation checklist and mandatory final validation phase.
3. Semantic fidelity mode for named libraries/benchmarks/formats.
4. Deadline-aware checkpointing and fallback mode for long tasks.
5. Cleanup-aware validation execution.
6. Media/data extraction confidence checks.
7. Domain-specific intermediate semantic assertions.
8. Prompt-cache monitoring as a regression guard.

The first two improvements should be implemented first because they cover the broadest set of failures and are likely to convert many "almost solved" tasks into passes without overfitting to any specific task.
