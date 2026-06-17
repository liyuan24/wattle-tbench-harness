# Terminal-Bench 2.0 Raw Failure Analysis

Generated from the GCP amd64 Wattle run `wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616`.

Snapshot used: `2026-06-17T11:22:34Z`

Counts at snapshot:

- Passed: 137
- Failed: 43
- Exceptions: 13
- Running or incomplete: 2
- Prompt-cache hit rate: 85.0%

Deep evidence reports were regenerated under:

```text
runs/gcp/wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616/analysis/failure_analysis/tasks/
```

The Codex comparison run `codex-compare-nonpassed-20260617` had twenty-two completed comparisons at this snapshot: Codex passed `build-pov-ray`, `db-wal-recovery`, `extract-moves-from-video`, `financial-document-processor`, `gcode-to-text`, `gpt2-codegolf`, `mteb-leaderboard`, `mteb-retrieve`, and `protein-assembly`; failed `configure-git-webserver`, `extract-elf`, `filter-js-from-html`, `install-windows-3.11`, `overfull-hbox`, `polyglot-c-py`, `polyglot-rust-c`, `raman-fitting`, `torch-tensor-parallelism`, `train-fasttext`, and `video-processing`; and timed out on `caffe-cifar-10` and `make-doom-for-mips`. No Codex comparisons were running at this snapshot. Most task notes remain grounded in Wattle logs, verifier failures, and Terminal-Bench oracle/tests.

## Confirmed Failures And Exceptions

### `build-pov-ray`

- Status: one Wattle attempt failed and one retry passed.
- Verifier: expected POV-Ray 2.2 source marker `file_id.diz`; it was missing, indicating the wrong extraction/build layout or wrong source version.
- Oracle contrast: downloads the exact `Official-2.2` `POVDOC`, `POVSCN`, and `POVSRC` archives, extracts them in `/app`, copies `machine/unix/*` into `source`, patches build files, and installs the resulting binary.
- Wattle behavior: the failed attempt reported a successful build and render but left the source tree in a layout the verifier considered wrong. Retry `build-pov-ray__w5rvtSs` passed after downloading official `POVSRC.TAR.Z` and `POVDOC.TAR.Z`, extracting to `/app/povray-2.2`, building under `/app/povray-2.2/build`, and validating the requested render command.
- Codex comparison: Codex passed this task, strengthening the conclusion that Wattle's failure is not a task/harness issue but a final-state provenance audit miss.
- Raw lesson: Wattle validated executable behavior without validating the verifier-visible provenance and required source artifacts.

### `caffe-cifar-10`

- Status: exception, `AgentTimeoutError`, in both synced Wattle attempts.
- Verifier: expected `/app/caffe/examples/cifar10/cifar10_quick_iter_500.caffemodel` and `/app/caffe/training_output.txt`; neither existed.
- Oracle contrast: installs Caffe dependencies, checks out BVLC Caffe at `9b89154`, applies CPU/OpenCV/HDF5 compatibility patches, builds Caffe, runs CIFAR data prep, then runs exactly 500 iterations with output tee'd to `training_output.txt`.
- Wattle behavior: the retry built CPU-only Caffe tools/examples and configured the solver for `max_iter: 500`, `snapshot: 500`, and CPU mode, but again timed out before producing the required caffemodel and `training_output.txt`.
- Raw lesson: long build/train tasks need earlier task-plan compression, deadline-aware fallbacks, and explicit artifact checkpoints before continuing expensive work.

### `configure-git-webserver`

- Status: failed in both synced Wattle attempts.
- Verifier: after its own clone/push/curl flow, the first Wattle attempt returned HTTP 404 and the retry returned HTTP 000.
- Oracle contrast: creates a bare repo at `/git/server`, deploys via `post-receive` to `/var/www/html`, and serves that root on port 8080.
- Wattle behavior: validated a manual flow, then reset repo/web-root state in the first attempt; the retry installed a hook and server but still did not leave the verifier's fresh workflow reachable.
- Codex comparison: Codex also failed this task with the same verifier-visible HTTP 404 pattern, which suggests the task is easy to invalidate with small service/root-state mismatches.
- Raw lesson: Wattle should preserve the final state required by the verifier, not reset after a smoke test unless the instruction explicitly requires reset.

### `db-wal-recovery`

- Status: failed.
- Verifier: `Apple` stayed at value `100`; expected WAL update value `150`, proving encrypted WAL changes were not applied.
- Oracle contrast: detects the XOR-encrypted WAL, XOR-decrypts it with key `0x42`, replaces `/app/main.db-wal`, then lets SQLite apply the WAL before writing `recovered.json`.
- Wattle behavior: produced valid-looking JSON with rows sorted by id, but from the base database state rather than recovered WAL state.
- Codex comparison: Codex passed this task, strengthening the conclusion that the task and harness are healthy and Wattle's miss is semantic recovery of sidecar WAL state.
- Raw lesson: Wattle should treat sidecar recovery files as first-class input and verify semantic deltas, not only output shape.

### `dna-assembly`

- Status: failed in both synced Wattle attempts.
- Verifier: first attempt's `primers.fasta` existed and had the expected primer inventory, but at least one forward/reverse pair had an annealing Tm delta of 5.071125 C, just above the allowed 5 C threshold. Retry `dna-assembly__eEHGCRK` failed the same contract with an even larger Tm delta of 7.260135 C.
- Oracle contrast: chooses exact template cut boundaries, excludes insert start/stop codons where required, derives Golden Gate overhangs from the verifier-equivalent reverse-complement reconstruction, and validates every annealing tract with `oligotm -tp 1 -sc 1 -mv 50 -dv 2 -n 0.8 -d 500`.
- Wattle behavior: both attempts did substantial correct setup work and reported that primer-pair Tm differences were within 5 C, but final local validation still did not match the verifier's reconstruction/orientation path. The retry explicitly tried to use Primer3 `oligotm`, which shows the remaining gap is likely in which annealing segment/orientation is validated, not just which Tm binary is used.
- Raw lesson: near-threshold scientific/design tasks need verifier-equivalent reconstruction with margin; Wattle should not accept a final design where an exact hidden check can fail by a small tolerance.

### `dna-insert`

- Status: failed in multiple synced Wattle attempts.
- Verifier: `primers.fasta` existed and encoded the insert, but the forward and reverse annealing Tm values differed by 6.531905 C, above the allowed 5 C. Newer attempt `dna-insert__aB9GhwR` repeated the same failure signature as `dna-insert__aGR64tR`.
- Oracle contrast: computes the reverse annealing segment in the primer/verifier orientation with `oligotm -tp 1 -sc 1 -mv 50 -dv 2 -n 0.8 -d 500`, writes exactly one forward/reverse pair, and validates the reconstructed `rc(reverse_primer) + forward_primer` insert plus vector overlaps.
- Wattle behavior: wrote a plausible one-pair FASTA and locally reported a 0.074115 C Tm difference, but its local check used the reverse annealing sequence orientation differently from the verifier.
- Raw lesson: scientific/design tasks need verifier-equivalent reconstruction and orientation checks, not only domain-plausible local validation.

### `extract-elf`

- Status: one Wattle attempt failed and one retry passed.
- Verifier: failed attempt matched only 0% of expected values.
- Oracle contrast: parses ELF headers, sections, symbol tables, memory words, function symbols, and address/function mappings using a full ELF parser.
- Wattle behavior: failed attempt emitted valid JSON with plausible numeric keys, but the data model did not match the expected ELF extraction contract. Retry `extract-elf__2EaaYvz` passed after investigating PIE load-base conventions and rebased versus base-independent addresses while implementing `/app/extract.js`.
- Codex comparison: Codex also failed this task with 0.00% expected values, reinforcing that superficial JSON/numeric extraction is a broad trap for binary-format tasks.
- Raw lesson: for binary formats, superficial output schema checks are insufficient; parser-backed extraction and explicit address-convention checks can turn a 0% semantic match into a pass.

### `extract-moves-from-video`

- Status: one Wattle attempt failed and one retry ended with `AgentTimeoutError`.
- Verifier: first attempt's solution text similarity was 63.37%, below the 90% threshold. Retry `extract-moves-from-video__Gd4fao8` timed out and verifier execution saw no `/app/solution.txt`, despite the last logged tool writing 1,797 bytes to that path.
- Oracle contrast: derives the Zork command transcript from the video rather than producing a merely plausible command list.
- Wattle behavior: first attempt wrote a syntactically clean `solution.txt`, but the extracted sequence was materially different. Retry spent more time on OCR/frame extraction but still did not leave a verifier-visible final artifact before timeout.
- Codex comparison: Codex passed this task, so the failure points to Wattle's video/transcript extraction strategy rather than a task or harness issue.
- Raw lesson: media/OCR tasks need confidence-aware extraction and cross-validation, and long extraction retries need final artifact persistence checks before timeout.

### `filter-js-from-html`

- Status: failed in both synced Wattle attempts.
- Verifier: missed XSS vectors and modified 5 clean HTML files.
- Oracle contrast: uses BeautifulSoup to remove dangerous tags and attributes while preserving benign structure.
- Wattle behavior: validated narrow samples and made a robustness pass for style/meta JavaScript, but still missed generated XSS vectors and modified clean files.
- Codex comparison: Codex also failed this task with missed XSS vectors and clean-file modifications, reinforcing that sanitizer tasks need explicit positive and negative regression suites.
- Raw lesson: when a task implies a filter/sanitizer, Wattle should build and run a representative adversarial and clean regression set before finalizing.

### `financial-document-processor`

- Status: exception, `NonZeroAgentExitCodeError`, in both synced Wattle attempts.
- Verifier: invoices and `summary.csv` were missing or incomplete in both attempts; retry `financial-document-processor__QTBG3Nt` still left `/app/invoices/summary.csv` missing.
- Oracle contrast: implements OCR/text extraction for images/PDFs, content-based invoice classification, moves every document, and writes a structured invoice summary.
- Wattle behavior: began moving hand-classified files and then exited before completing destination directories and summary output. Retry again reached the "move files and write CSV" phase, but verifier-visible state still lacked the summary.
- Codex comparison: Codex passed this task, showing the transaction-style all-files-then-summary workflow is achievable in the same task environment.
- Raw lesson: multi-file classification tasks need transaction-style staging: classify all files, validate total coverage, then move/write outputs atomically.

### `gcode-to-text`

- Status: failed in both synced Wattle attempts.
- Verifier: expected `flag{gc0d3_iz_ch4LLenGiNg}`. The first attempt wrote `the quick brown fox jumps over the lazy dog`; retry `gcode-to-text__BRWtjtt` wrote the near-flag string `flag{gac0d3_iz_ch4LLengING}`.
- Oracle contrast: renders rotated 3D G-code segments and uses image/OCR tooling to recover the hidden text.
- Wattle behavior: moved from a plausible sentence to a nearly correct flag-shaped output, but still accepted character-level OCR/geometry errors that the verifier rejected.
- Codex comparison: Codex passed this task, confirming the hidden flag is recoverable in the same environment when the rendering/OCR workflow is strong enough.
- Raw lesson: Wattle should avoid accepting plausible or near-correct OCR/vision output without task-specific character-level validation, expected-pattern checks, and alternative views/renderings.

### `gpt2-codegolf`

- Status: failed in three synced Wattle attempts.
- Verifier: `gpt2.c` did not satisfy the full compile/run contract.
- Oracle contrast: provides a dense under-5000-byte GPT-2 implementation with the exact expected CLI and checkpoint/vocab reading behavior.
- Wattle behavior: created small C implementations and smoke-tested them, but all completed Wattle trials failed the verifier. Two attempts failed the verifier-visible artifact/path/compile contract, including retry `gpt2-codegolf__bNUptDs` despite reporting `/app/gpt2.c` size and compile checks locally; another attempt passed size/compile locally but failed the semantic expected-continuation check for a known verifier prompt.
- Codex comparison: Codex passed the same task in the comparison run, which suggests the harness/task is healthy and Wattle's miss is in exact contract execution rather than environment setup.
- Raw lesson: code-golf/implementation tasks need verifier-like command reproduction and semantic output checks, including exact file path, argv, size, compile flags, tokenization, checkpoint layout, BPE mapping, and expected continuation contract.

### `install-windows-3.11`

- Status: one Wattle attempt exited non-zero and one retry failed.
- Verifier: first attempt had no QEMU process and no VNC listener on 5901. Retry left QEMU/VNC/nginx/noVNC running with `/app/isos/win311.img`, but failed `test_windows_keys_with_visual_feedback`.
- Oracle contrast: compiles/uses QEMU 5.2.0, starts the Windows image with the required legacy device flags, VNC `:1`, nginx/noVNC service, and monitor interfaces.
- Wattle behavior: first attempt investigated boot flags but did not leave the required long-running VM services alive. Retry improved final liveness and path correctness but still missed keyboard/visual-feedback behavior.
- Codex comparison: Codex also failed the verifier, with QEMU running against `/app/win311-runtime.img` instead of the expected `/app/isos/win311.img`, plus visual-feedback key tests failing.
- Raw lesson: service tasks need a final liveness gate for all required processes/ports after any debugging restarts.

### `make-doom-for-mips`

- Status: exception, `AgentTimeoutError`, in both synced Wattle attempts.
- Verifier: retry still missed expected VM stdout `I_InitGraphics: DOOM screen size: w x h: 320 x 200` and produced a frame similarity score 0.7339 below the 0.95 requirement.
- Oracle contrast: applies a large MIPS build patch, supplies custom libc/runtime pieces, cross-compiles, and validates under the JS VM.
- Wattle behavior: first attempt built a MIPS binary and generated a frame, but execution stopped on an unsupported instruction. Retry produced `/app/doomgeneric_mips`, reached partial Doom startup, and wrote `/tmp/frame.bmp`, but still missed the expected graphics-init milestone and reference-like frame.
- Codex comparison: Codex also timed out. Its verifier output reached Doom initialization but still missed the expected graphics initialization text `I_InitGraphics: DOOM screen size: w x h: 320 x 200`.
- Raw lesson: emulator/cross-compile tasks need early ISA/runtime compatibility checks and a plan to minimize late-cycle debugging.

### `mcmc-sampling-stan`

- Status: one Wattle attempt timed out with bad final artifacts and one retry passed.
- Verifier: failed attempt's posterior alpha and beta means were astronomically wrong relative to expected ranges, despite Wattle reporting plausible mean files before timeout.
- Oracle contrast: installs pinned RStan dependencies, uses a hierarchical binomial Stan model with the intended prior transformation, then runs a long reproducible sample to write posterior means.
- Wattle behavior: failed attempt generated the required files and an apparently good intermediate result, then changed the Stan model/rerun path and timed out with verifier-visible bad posterior files. Retry `mcmc-sampling-stan__puVs8Uq` passed with RStan 2.32.7, `rstan::sampling`, 4 chains, 100,000 iterations, seed 1, and final means `alpha = 2.871847972980092`, `beta = 16.35229149756377`.
- Raw lesson: probabilistic/scientific tasks need stable final artifact protection; once a verifier-plausible result is produced, later experiments should not overwrite it without passing the same checks. The retry shows that a pinned oracle-like path plus preserved final artifacts can recover the task.

### `model-extraction-relu-logits`

- Status: one Wattle attempt failed and one retry passed.
- Verifier: `stolen_A1.npy` existed, but row 11 of the verifier's original 30x10 matrix could not be matched up to scaling.
- Oracle contrast: uses query-only ReLU critical-point sweeps that are robust to unknown hidden width and verifier-generated weights.
- Wattle behavior: failed attempt produced a script and locally validated perfect recovery against the visible `/app/forward.py` internals, including a visible 20x10 `A1`, but the verifier used a different generated matrix and exposed incomplete row recovery. Retry `model-extraction-relu-logits__ZuPA7xn` passed after re-running `/app/steal.py`, saving `/app/stolen_A1.npy`, and validating recovered row directions against local `forward.A1`.
- Raw lesson: model-extraction tasks need hidden-input robustness checks and should not rely on visible implementation constants as proof of correctness; the retry shows the task can be recovered when the query-based kink extraction is made complete enough for the verifier-generated matrix.

### `mteb-leaderboard`

- Status: failed in both synced Wattle attempts.
- Verifier: expected `GritLM/GritLM-7B`; both Wattle attempts wrote `Salesforce/SFR-Embedding-2_R`.
- Oracle contrast: checks out the MTEB results repo at a specific commit, loads the exact `MTEB(Scandinavian, v1)` benchmark, filters models with all tasks, and computes complete-task averages.
- Wattle behavior: selected a plausible leaderboard winner twice, including after inspecting benchmark/task definitions in the retry, but still did not reproduce the exact dated result computation.
- Codex comparison: Codex passed this task, strengthening the conclusion that Wattle needs exact benchmark snapshot/completeness/aggregation reproduction rather than a broader leaderboard heuristic.
- Raw lesson: benchmark/leaderboard tasks require exact dataset snapshot, benchmark name, completeness filters, and aggregation semantics.

### `mteb-retrieve`

- Status: failed in both synced Wattle attempts.
- Verifier: expected `MTEB: Massive Text Embedding Benchmark`; Wattle wrote `HumanEval: Benchmarking Python code generation via functional examples`.
- Oracle contrast: uses `mteb.get_model("BAAI/bge-small-zh-v1.5", revision=...)`, encodes query with `task_name="SciFact"` and `PromptType.query`, encodes docs with `PromptType.passage`, then selects the 5th highest similarity.
- Wattle behavior: inspected model/wrapper details but still wrote the wrong document in both attempts; retry `mteb-retrieve__Mr7e9Et` also synced the same unexpected result.
- Codex comparison: Codex passed this task in the comparison run, which reinforces that the failure is not the harness or task image but Wattle's exact MTEB API/revision/prompt-type/ranking reproduction.
- Raw lesson: embedding tasks are sensitive to wrapper semantics, prompt type, task name, revision, and ranking convention; Wattle needs exact API parity with the prompt/oracle.

### `overfull-hbox`

- Status: two Wattle attempts failed and one retry passed.
- Verifier: modified `input.tex` using `veteran`, which was not an allowed synonym replacement for `old`.
- Oracle contrast: parses `main.log`, builds substitutions only from `synonyms.txt`, repeatedly compiles and substitutes one allowed synonym until no overfull boxes remain.
- Wattle behavior: failed attempts achieved no overfull hbox warnings but violated the allowed-edit contract. Retry `overfull-hbox__iv3p9dd` passed after editing only `input.tex`, preserving `main.tex` and `synonyms.txt`, recompiling, and verifying no `Overfull \hbox` warnings.
- Codex comparison: Codex also failed this task with the same allowed-edit contract pattern, replacing `old` with `veteran` even though that synonym was not present in `synonyms.txt`.
- Raw lesson: validation should check both the desired effect and the permitted transformation set.

### `polyglot-c-py`

- Status: failed.
- Verifier: expected only `main.py.c`; found an extra `cmain`.
- Oracle contrast: creates only `polyglot/main.py.c`; compiled binaries are not left in the target directory.
- Wattle behavior: created the correct source and validated it, but left build artifacts in the directory the verifier checks.
- Codex comparison: Codex also failed with the same leftover `cmain` artifact, reinforcing that exact final inventory is a general agent failure mode.
- Raw lesson: Wattle needs cleanup/final-state hygiene after validation, especially in tasks with exact directory contents.

### `polyglot-rust-c`

- Status: failed in all three synced Wattle attempts.
- Verifier: expected only `main.rs`; found `main`, `cmain`, and `main.rs`.
- Oracle contrast: creates only `polyglot/main.rs`; build products are not left in place.
- Wattle behavior: validated both Rust and C++ compilation but left generated executables/symlinks. Retry `polyglot-rust-c__ciAfnzW` repeated the same failure signature by leaving `cmain`, `main`, and `main.rs`.
- Codex comparison: Codex also failed the task with the same final-inventory contract class, leaving `main` beside `main.rs`. That makes the failure pattern broader than Wattle-specific execution cleanup.
- Raw lesson: exact output inventories should be treated as part of the task contract, not incidental filesystem state.

### `protein-assembly`

- Status: failed in both synced Wattle attempts.
- Verifier: fusion protein order was wrong in both attempts; expected flag, donor, DHFR, acceptor, SNAP.
- Oracle contrast: identifies binder/tag semantics, resolves SNAP/fluorescent protein choices from external sequence sources, then assembles the sequence in the specified order.
- Wattle behavior: generated valid DNA-looking `gblock.txt` files and locally reported the intended component order in both attempts, but the verifier still could not find the required order, showing Wattle's component identity check was not verifier-equivalent.
- Codex comparison: Codex passed this task, so the required component-order grounding is achievable under the same task/harness.
- Raw lesson: bio/design tasks need semantic validation against named components and ordering, not only sequence validity.

### `pytorch-model-recovery`

- Status: failed.
- Verifier: TorchScript `forward()` expected at most 2 arguments but received 3; the expected recovered model interface accepts source and target tensors.
- Oracle contrast: reconstructs the transformer-style architecture from `weights.pt`, including `forward(self, src, tgt)`, tunes only `output_layer`, then saves `/app/model.pt` as TorchScript.
- Wattle behavior: produced a TorchScript model with a single-input forward signature, so it could not be called by the verifier's dataset path.
- Raw lesson: model-recovery tasks need exact module interface validation, not only state-dict loading and local loss checks.

### `raman-fitting`

- Status: failed in both synced Wattle attempts; Codex comparison also failed.
- Verifier: expected G peak near `x0=1580.3`, `gamma=9.06`, `A=8382.69`, `offset=5561.03`, and 2D peak near `x0=2670.08`, `gamma=17.52`, `A=12314.42`, `offset=1239.09`. Wattle retry still produced peaks near `x0=1654.86` and `x0=3745.36`.
- Oracle contrast: converts decimal commas/tab format, converts wavelength nm to cm^-1, crops G and 2D peak regions, then fits Lorentzian peaks with SciPy.
- Wattle behavior: produced JSON with fit parameters, but used the wrong x-axis transformation/crop/model setup across attempts; the retry's narrower-region attempt still converged to the same wrong observed peaks.
- Codex comparison: Codex also failed this task, fitting broad wrong peaks with much larger gammas and offsets. This reinforces that scientific preprocessing/window selection must be explicit, not left to generic curve fitting.
- Raw lesson: numerical science tasks need unit conversion and range checks before fitting; output plausibility is not enough.

### `sam-cell-seg`

- Status: failed in both synced Wattle attempts.
- Verifier: first attempt passed the substantive geometry checks but failed `test_coords_are_flat_lists`: row 0 `coords_x` parsed as a tuple instead of a list. Retry `sam-cell-seg__7DkFdAV` still failed the same flat-list serialization check and also failed `test_mask_alignment` with IoU 0.464338 below the 0.5 threshold.
- Oracle contrast: uses MobileSAM box prompts, resolves overlaps/contiguity, then writes `coords_x` and `coords_y` as flat list-like fields accepted by the verifier.
- Wattle behavior: solved much of the segmentation workflow, but did not validate serialized coordinate fields by reading the output CSV exactly as the verifier does. The retry also shows the image-mask path is near a geometry threshold and needs verifier-like IoU/alignment validation, not only "polyline/non-overlap/contiguity" structural checks.
- Raw lesson: Wattle needs final output-type/schema validation at the serialized artifact level and threshold-aware image-mask validation against the verifier's scoring path.

### `torch-tensor-parallelism`

- Status: failed.
- Verifier: gradient mismatch for both column and row parallel linear layers.
- Oracle contrast: implements Megatron-style autograd collectives: copy input forward/all-reduce gradient backward, gather output forward/split gradient backward, reduce output forward/identity backward.
- Wattle behavior: passed basic syntax/forward-style checks but failed distributed gradient semantics.
- Codex comparison: Codex also failed this task, with row-parallel failures across multi-rank cases. This reinforces that the task requires exact distributed autograd semantics, not just Wattle-specific cleanup.
- Raw lesson: framework tasks need backward-pass tests and multi-rank numerical equivalence, not only import/forward smoke tests.

### `train-fasttext`

- Status: exception, `AgentTimeoutError`, in both synced Wattle attempts.
- Verifier: first Wattle attempt had private accuracy 0.539925 and retry had 0.602975, both below threshold 0.62.
- Oracle contrast: converts the provided parquet train set to FastText supervised format and trains with `wordNgrams 2` and `dim 5`.
- Wattle behavior: first attempt reported acceptable validation on its own processed split, but verifier used the real private evaluation contract and failed. Retry produced a smaller valid model but still missed the accuracy threshold before timeout.
- Codex comparison: Codex also failed, with private accuracy 0.58465 below the same 0.62 threshold. This makes the issue broader than Wattle-only execution and reinforces the need for exact data conversion/training settings and validation with margin.
- Raw lesson: ML tasks need validation that matches the verifier input format and threshold with margin; internal split success can be misleading.

### `video-processing`

- Status: failed in both synced Wattle attempts.
- Verifier: first attempt had landing frame 230 outside inclusive range 231 to 234; retry had example landing frame 61 below range 62 to 64 and test-video takeoff frame 239 above range 219 to 223.
- Oracle contrast: uses frame-level movement/background subtraction and task-specific thresholds to locate jump start/end.
- Wattle behavior: produced the required TOML structure and plausible frame estimates, but failed tight temporal boundaries in different ways across attempts.
- Codex comparison: Codex also failed a tight boundary check, but on takeoff rather than landing: takeoff frame 226 was outside the inclusive range 219 to 223.
- Raw lesson: video/temporal tasks need exact boundary calibration and verifier-range checks before final answer.

## Completed Passing Retries Since Prior Snapshot

### `break-filter-js-from-html`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `break-filter-js-from-html__UQZyZ5A` completed successfully after creating `/app/out.html` and `/app/alert.html`, validating the same copy-filter-open flow as the provided test with `/app/filter.py`, and detecting automatic `alert(1)` in Chromium. Earlier attempts `break-filter-js-from-html__wwLsocx` and `break-filter-js-from-html__pPj3PwT` passed with different parser/browser differential payloads that survived filtering and triggered automatic alerts.
- Oracle contrast: uses a malformed HTML comment that the filter mishandles but Chromium still parses into executable script.
- Raw lesson: this remains a positive example for parser-differential adversarial validation; it does not change the general failure taxonomy.

### `write-compressor`

- Status: passed in both synced Wattle attempts.
- Current evidence: the retry `write-compressor__kXTZ9Z9` completed successfully after producing `/app/data.comp` at 2280 bytes and validating that `cat data.comp | /app/decomp` exactly matches `/app/data.txt`. The earlier pass produced a 2476-byte `data.comp`.
- Oracle contrast: reverse-engineers the decompressor format and emits a compact compressed stream below the 2500-byte limit.
- Raw lesson: this remains a positive example for exact executable-output validation against a strict size budget; it does not change the general failure taxonomy.

### `reshard-c4-data`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `reshard-c4-data__waCkgeY` completed successfully after creating `/app/compress.py`, `/app/decompress.py`, `/app/pyproject.toml`, `/app/uv.lock`, and a uv environment; it validated `/app/c4_sample` compression/decompression round-trip, max 30 entries per directory, max file size `15000000` bytes, and exact restored-file comparison. Earlier attempts passed with the same round-trip, fanout, file-size, and `.reshard_*` edge-case validation.
- Oracle contrast: writes `compress.py`, `decompress.py`, `pyproject.toml`, and uv metadata so the archive can be compressed and then reconstructed exactly in-place under the task's directory and file-size constraints.
- Raw lesson: this remains a positive example for verifier-like artifact and round-trip validation under filesystem constraints; it does not change the general failure taxonomy.

### `merge-diff-arc-agi-task`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `merge-diff-arc-agi-task__dmQXSds` completed successfully after initializing `/app/repo`, fetching both bundles into `branch1` and `branch2`, checking out `branch1`, merging `branch2`, resolving `/app/repo/algo.py`, validating all three examples, committing the merge, and leaving a clean Git status with both branches present. Earlier attempts `merge-diff-arc-agi-task__6XScxMA` and `merge-diff-arc-agi-task__ofUGtxY` also passed with the same branch setup and example validation.
- Oracle contrast: creates `branch1` and `branch2` from the bundles, uses branch1 as base, applies the branch2 state, then implements `algo.py` with a modulo-diagonal color mapping inferred from examples.
- Raw lesson: this remains a positive example for exact repository-state setup plus verifier-like example validation; it does not change the general failure taxonomy.

### `pytorch-model-cli`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `pytorch-model-cli__h3Hw5Xx` completed successfully after creating `/app/cli_tool`, `/app/weights.json`, and `/app/prediction.txt`, validating that `./cli_tool weights.json image.png` outputs only `2`, and confirming the prediction artifact contains only `2`. Earlier attempts `pytorch-model-cli__Ppsm6C6` and `pytorch-model-cli__j8TEW5F` passed with the same exact executable, weights, CLI output, and artifact contract.
- Oracle contrast: builds a CLI around the supplied image/model assets, writes the expected prediction artifact, and preserves the exact command interface.
- Raw lesson: this remains a positive example for exact final command and artifact validation; it does not change the general failure taxonomy.

### `largest-eigenval`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `largest-eigenval__pXaQN7X` completed successfully after implementing a SciPy low-level LAPACK `dgeev` path with complex-vector reconstruction, NumPy fallback, direct `1x1` handling, and correctness/speed validation over random, identity, zero, triangular, and block matrices. Earlier attempts `largest-eigenval__Vd5wSwF` and `largest-eigenval__A5bGYJK` passed with NumPy LAPACK-backed paths, dominant-eigenvalue selection by magnitude, right-eigenvector returns, and `/app/eval.py` correctness and speed validation.
- Oracle contrast: implements the dominant eigenpair function with exact correctness and performance constraints against the evaluation harness.
- Raw lesson: this remains a positive example for pairing performance optimization with verifier-like correctness checks across matrix sizes; it does not change the general failure taxonomy.

### `portfolio-optimization`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `portfolio-optimization__CkMJU5V` completed successfully after implementing and validating the optimized C extension, preserving the public Python wrapper API, building with `python3 setup.py build_ext --inplace`, and passing `python3 benchmark.py`. Earlier attempts `portfolio-optimization__3N3WX9B` and `portfolio-optimization__e5C3zxs` passed with the same C-backed risk/return implementation and validation path.
- Oracle contrast: implements fast C-backed portfolio risk and return functions while preserving the exact Python wrapper contract and benchmark correctness.
- Raw lesson: this remains a positive example for exact wrapper-preserving optimization plus benchmark validation; it does not change the general failure taxonomy.

### `path-tracing-reverse`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `path-tracing-reverse__yNGZHkV` completed successfully after writing `/app/mystery.c`, compiling with `gcc -static -O2 -o reversed mystery.c -lm`, comparing original `/app/mystery` and `/app/reversed` in separate temp directories, matching exit code, stdout, stderr, and `image.ppm` byte-for-byte, and keeping compressed source under 2k. Earlier attempts `path-tracing-reverse__PfxM9GJ` and `path-tracing-reverse__K2cVozH` passed with the same standalone-source, static-compile, byte-level image/progress validation.
- Oracle contrast: reconstructs a compact C renderer that reproduces the hidden path-tracing output and progress behavior under the compressed-size constraint.
- Raw lesson: this remains a positive example for exact behavioral reproduction plus compressed-source validation; it does not change the general failure taxonomy.

### `path-tracing`

- Status: two completed Wattle attempts passed and one retry is running.
- Current evidence: retry `path-tracing__dhCWrsR` completed successfully after writing `/app/image.c`, compiling it, generating `reconstructed.ppm`, keeping compressed source at `3 19 644` from `cat image.c | gzip | wc`, validating output dimensions `2400x1800`, and reaching local relative-L2-style similarity `0.9929`. The earlier pass `path-tracing__iZaeUpX` also generated `/app/reconstructed.ppm`, stayed under 2k compressed, and reached high normalized-L2 similarity. Running retry `path-tracing__fp6agpu` is fitting camera, checker plane, sphere, and lighting parameters from pixel samples before implementing a compact `image.c` and validating with an independent similarity script.
- Oracle contrast: writes a compact C image generator that reconstructs the target path-traced image closely enough under the compressed-size limit.
- Raw lesson: this remains a positive example for compact generator validation against image similarity and source-size constraints; it does not change the general failure taxonomy.

### `distribution-search`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `distribution-search__SxWGnVN` completed successfully after creating `/app/create_dist.py` and `/app/dist.npy`, validating shape `(150000,)`, dtype `float64`, positive finite probabilities summing to `0.99999999999999989`, and forward/backward KL divergences of `9.9999999999984439` and `9.9999999999966143`. The earlier pass `distribution-search__vH5iCnP` validated the same shape, probability, and KL constraints.
- Oracle contrast: constructs the exact probability vector satisfying both KL constraints within tolerance.
- Raw lesson: this remains a positive example for exact numeric constraint validation with tolerance margins; it does not change the general failure taxonomy.

### `adaptive-rejection-sampler`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `adaptive-rejection-sampler__E68fkod` completed successfully after installing R, implementing `/app/ars.R`, generating `/app/normal_samples.txt`, and running the formal `test()` function through `Rscript`. The earlier pass `adaptive-rejection-sampler__joi43Xi` validated normal, exponential, invalid-input, and non-log-concavity behavior.
- Oracle contrast: implements the adaptive rejection sampler in R with validation over target distributions and invalid inputs.
- Raw lesson: this remains a positive example for installing missing runtime dependencies and running the task's formal statistical validation; it does not change the general failure taxonomy.

### `custom-memory-heap-crash`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `custom-memory-heap-crash__3QLCZxW` completed successfully after modifying only `/app/user.cpp`, forcing libstdc++ facet registration before the custom heap is enabled, calling `__gnu_cxx::__freeres()` in cleanup, and validating Release, Debug, and Valgrind with zero reported errors. The earlier pass fixed the same release-only custom-heap cleanup crash.
- Oracle contrast: fixes the release-only teardown crash without changing the protected allocator owner code.
- Raw lesson: this remains a positive example for root-cause validation across build modes plus memory tooling; it does not change the general failure taxonomy.

### `regex-chess`

- Status: two completed Wattle attempts passed and one retry is running.
- Current evidence: retry `regex-chess__e3gJsr6` completed successfully after writing `/app/re.json` as a JSON list of regex/replacement pairs, validating the sample output, passing `/app/check.py`, satisfying the pair-count and size limits, and passing additional valid-position comparisons against `python-chess` for castling, queen promotion, and en-passant cases. The earlier pass `regex-chess__eBbYn7d` generated 6,863 pairs and passed the same checker. Running retry `regex-chess__Zv766pg` has inspected the checker behavior and is generating regex rules that expand FEN, emit candidate next positions, filter illegal king-in-check positions, and recompress.
- Oracle contrast: generates a regex/pattern inventory that makes the chess PGN checker pass while preserving the exact JSON interface expected by the tests.
- Raw lesson: this remains a positive example for matching the verifier's normalization contract and then broadening validation over legal edge cases; it does not change the general failure taxonomy.

### `modernize-scientific-stack`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `modernize-scientific-stack__yXQwSEJ` completed successfully after creating `/app/analyze_climate_modern.py` and `/app/requirements.txt`, using Python 3 syntax, reading CSV data with pandas and UTF-8 encoding, using `pathlib.Path` and `configparser`, processing stations `101` and `102`, and validating the required mean-temperature output. Earlier attempts `modernize-scientific-stack__mWcAi6j` and `modernize-scientific-stack__wrSjEGR` passed with the same data/config behavior and legacy-file preservation.
- Oracle contrast: modernizes the scientific stack while preserving the same data/config behavior and expected output without modifying the legacy file.
- Raw lesson: this remains a positive example for preserving legacy behavior while modernizing dependencies and syntax; it does not change the general failure taxonomy.

### `torch-tensor-parallelism` retry

- Status: mixed completed outcomes: one Wattle retry passed, and two Wattle attempts failed distributed gradient/indexing checks.
- Current evidence: retry `torch-tensor-parallelism__9Nbajku` failed with `ColumnParallelLinear` weight-gradient mismatch on rank 0 and `RowParallelLinear` slicing failure (`start (16) + length (16) exceeds dimension size (16)`) after only syntax-validating `/app/parallel_linear.py`. Earlier failed attempt `torch-tensor-parallelism__gbSTPtC` also missed column/row parallel weight gradients. Retry `torch-tensor-parallelism__DJJCv6Q` passed after implementing sharded column/row parallel layers plus custom autograd wrappers for gather/reduce behavior so local weight and bias gradients are preserved. Codex also failed row-parallel indexing/shape behavior.
- Oracle contrast: implements Megatron-style distributed linear layers with exact forward and backward collective semantics across ranks.
- Raw lesson: this is positive evidence that exact distributed autograd semantics can turn the task around, but it still supports the broader need for multi-rank/backward verifier-like validation.

### `feal-linear-cryptanalysis`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `feal-linear-cryptanalysis__eX5XQT8` completed successfully after recovering the 20-bit seeds, expanding round keys, validating encryption/decryption across all 32 known pairs, generating `/app/plaintexts.txt` from `/app/ciphertexts.txt`, and confirming 100 output lines. The earlier pass `feal-linear-cryptanalysis__9FwPG5V` recovered the same seeds and validated the same plaintext output.
- Oracle contrast: recovers the FEAL key material from known pairs and writes the exact decrypted plaintext list.
- Raw lesson: this remains a positive example for end-to-end cryptanalytic validation against all known pairs plus final output cardinality; it does not change the general failure taxonomy.

### `prove-plus-comm`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `prove-plus-comm__ZNbd2W4` completed successfully after replacing the base-case `admit` with `apply plus_n_O`, replacing the inductive-step `admit` with `rewrite IHn'` and `apply plus_n_Sm`, running `coqc plus_comm.v`, and confirming `plus_comm.vo` was produced. The earlier pass `prove-plus-comm__bvZWpuh` completed and compiled the same proof.
- Oracle contrast: completes the Coq proof without admits and leaves the compiled proof artifact.
- Raw lesson: this remains a positive example for exact compiler-backed proof validation; it does not change the general failure taxonomy.

## Completed Mixed-Outcome Retries Since Prior Snapshot

### `winning-avg-corewars` retry

- Status: mixed outcome: two Wattle attempts passed, and one retry ended with `AgentTimeoutError`.
- Current evidence: retry `winning-avg-corewars__eL6NiVq` passed after final validation with the required `pmars -b -r 100 -f my_warrior.red warriors/<opponent>.red` command form, meeting thresholds against stone, vampire, paper, snake, and G2-Clear. Earlier pass `winning-avg-corewars__Figpaws` also validated above all required win thresholds. Retry `winning-avg-corewars__KJ5akir` timed out after a bounded search; its final state left an early placeholder/test `my_warrior.red` that the verifier scored at 0% against `stone.red`, while the best temporary candidate still missed the `snake` and `g2-clear` thresholds.
- Oracle contrast: writes a multi-component Redcode warrior and validates against stone, vampire, paper, snake, and G2-Clear without modifying opponent files.
- Raw lesson: when search does not find a fully validated candidate before timeout, Wattle should not leave placeholder/test artifacts as the verifier-visible final answer. It should either preserve the best fully validated deliverable or clearly fail without an invalid placeholder.

### `pypi-server`

- Status: one Wattle attempt failed and one retry passed.
- Current evidence: failed attempt `pypi-server__5YR7FXj` produced a wheel and local simple index and locally validated `pip install`, but the verifier's `pip install --index-url http://localhost:8080/simple vectorops==0.1.0` returned non-zero. Retry `pypi-server__HoQwWjN` passed after using a `src/vectorops` package layout, placing the wheel under `pypi/simple/vectorops/`, and validating the server on port 8080.
- Oracle contrast: serves a PyPI-compatible simple index on port 8080 with the expected package/version/function import contract.
- Raw lesson: package-index tasks need verifier-exact index layout and install command validation, not only a local package build or manually tested alternate layout.

### `make-mips-interpreter`

- Status: one Wattle attempt passed and one retry failed.
- Current evidence: passed attempt `make-mips-interpreter__aCajDDM` implemented `/app/vm.js`, booted Doom through graphics initialization, saved `/tmp/frame.bmp`, and validated the BMP header, `640 x 400` resolution, and 32-bit depth. Retry `make-mips-interpreter__e9PC8ee` also wrote a valid-size BMP and reported graphics initialization, but the verifier did not find exact stdout `I_InitGraphics: DOOM screen size: w x h: 320 x 200` and measured frame similarity `0.8065` below the required `0.95`.
- Oracle contrast: implements enough MIPS VM behavior to run DoomGeneric and emit the exact expected graphics-init trace and reference-like frame artifact.
- Raw lesson: emulator/interpreter tasks need verifier-exact stdout and artifact-similarity checks; a booting program and valid image container are not sufficient proof.

## Newly Completed Passing Retries

### `cobol-modernization`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle implemented `/app/program.py`, preserved COBOL fixed-width no-newline `.DAT` records, updated account/book/transaction data, and compared Python outputs byte-for-byte against the original COBOL program from identical copied inputs.
- Oracle contrast: reimplements the COBOL data-processing behavior in Python while preserving exact fixed-width data files and transaction semantics.
- Raw lesson: this is positive evidence for a robust pattern: for legacy-program modernization tasks, Wattle should execute the original implementation as an oracle where available and compare final persisted artifacts byte-for-byte.

### `crack-7z-hash`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle recovered the password and wrote `/app/solution.txt` with the expected secret content `honeybear`; the retry also confirmed the target path `secrets/secret_file.txt` before finishing.
- Oracle contrast: recovers the 7z password and extracts only the target secret file content into the required solution artifact.
- Raw lesson: targeted artifact extraction and a minimal final answer file work well when Wattle keeps the verifier-visible deliverable narrow.

### `headless-terminal`

- Status: both synced Wattle attempts passed.
- Current evidence: passed attempt `headless-terminal__LZLy2Dd` implemented `HeadlessTerminal(BaseTerminal)` using a real PTY-backed interactive `/bin/bash -i`, installed `pexpect`/`ptyprocess`, and validated command echo, interactive `read`, `.bashrc` sourcing, and Ctrl-C handling.
- Oracle contrast: implements a headless terminal abstraction that behaves like an interactive terminal, not only a shell-command wrapper.
- Raw lesson: when the task requires interactive behavior, Wattle succeeded by validating through a real PTY and testing interactive control flows, not just subprocess output.

### `compile-compcert`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle built upstream CompCert tag `v3.13.1` under `/tmp/CompCert`, produced `/tmp/CompCert/ccomp`, installed the required runtime/config pieces, and validated the compiler through `ccomp -version` plus smoke C programs compiled from outside the source tree.
- Oracle contrast: builds the requested CompCert release at the required filesystem path and leaves the compiler invocable for verifier use.
- Raw lesson: build-heavy tasks can pass when Wattle keeps to a narrow upstream release path, validates the exact required executable path, and confirms invocation from outside the build directory.

### `schemelike-metacircular-eval`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle implemented `eval.scm`, preserved STDIN for interpreted programs, handled closures/environments/mutation/file I/O, compared direct `interp.py` output against `eval.scm` and nested self-interpretation, and removed generated callback artifacts.
- Oracle contrast: implements a Scheme-level evaluator that can run target programs through the provided interpreter while preserving observable behavior.
- Raw lesson: interpreter tasks benefit from differential validation against the baseline interpreter across the whole provided test corpus, plus cleanup of artifacts produced by tests.

### `git-multibranch`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle configured SSH remote `git@localhost:/git/project`, password auth, a bare repo, `post-receive` deployment for `main` and `dev`, and HTTPS nginx on port 8443, then cleaned validation-created refs/deployed payloads while preserving services and hooks.
- Oracle contrast: leaves a Git/HTTPS service state that lets the verifier push branches and observe the correct branch-specific deployed content.
- Raw lesson: service tasks can pass when Wattle validates the exact external workflow but then resets only validation payloads, not the required service/hook infrastructure.

### `qemu-startup`

- Status: one Wattle attempt passed and one retry timed out.
- Current evidence: passed attempt `qemu-startup__3XE3wqu` left QEMU running in the background and validated that `telnet 127.0.0.1 6665` showed an Alpine login prompt. Retry `qemu-startup__DsGusbV` timed out with QEMU no longer running, port 6665 not ready, and `/tmp/data.txt` missing during verifier execution.
- Oracle contrast: leaves the VM process and serial/telnet endpoint alive for the verifier's final liveness and version checks.
- Raw lesson: service/VM tasks need final liveness checks that run immediately before final response, and those checks must verify all required side artifacts as well as the visible port.

### `qemu-alpine-ssh`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle left Alpine running in QEMU with SSH forwarded on `localhost:2222`, root password `password123`, and validated an SSH login to a root shell inside the VM.
- Oracle contrast: leaves a booted VM with reachable SSH, not only a configured disk or launch command.
- Raw lesson: VM service tasks pass when Wattle validates the exact externally reachable login path and leaves the long-running process alive for the verifier.

### `circuit-fibsqrt`

- Status: both synced Wattle attempts passed.
- Current evidence: passed attempt `circuit-fibsqrt__HA3mGv6` created `/app/gates.txt` with 10,094 lines, validated the supplied simulator examples `sim 208 -> 377` and `sim 20000 -> 1407432322`, and checked 42 boundary/random inputs against a Python reference for `fib(isqrt(N)) mod 2^32`. Retry `circuit-fibsqrt__aQM8Ahy` also passed with an 8,100-line `gates.txt`, the same two official examples, and 38 independent edge/random reference checks.
- Oracle contrast: produces a gate network that matches the arithmetic contract under the simulator and line budget.
- Raw lesson: circuit-generation tasks can pass when Wattle validates both official examples and independently generated edge/random cases against a compact reference.

### `torch-pipeline-parallelism`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle implemented `train_step_pipeline_afab`, balanced contiguous layer partitioning, AFAB scheduling, P2P send/recv, loss scaling, backward gradient communication, and shape/target broadcasting for downstream stages.
- Oracle contrast: implements pipeline-parallel training semantics compatible with common Hugging Face LLaMA internals and distributed P2P behavior.
- Raw lesson: distributed training tasks can pass when Wattle validates the exact forward/backward communication contract rather than only local module syntax.

### `tune-mjcf`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle saved `/app/model.xml` with MuJoCo solver/computation settings that preserved physical model properties, validated `/app/eval.py` with final state difference 0.0000, and achieved speedups above 2x. Retry also ran an extra 30-seed correctness check with max absolute state difference `4.34e-08`.
- Oracle contrast: improves simulation runtime without changing the final full physics state beyond evaluator tolerance.
- Raw lesson: performance-tuning tasks can pass when Wattle changes solver/computation settings while validating exact state equivalence and runtime target together.

### `kv-store-grpc`

- Status: both synced Wattle attempts passed.
- Current evidence: Wattle created `kv-store.proto`, generated Python gRPC stubs, launched `/app/server.py` on port 5328, and validated `SetVal`, `GetVal`, and missing-key behavior through a real gRPC client.
- Oracle contrast: exposes the required gRPC service interface and leaves the server process running for verifier RPCs.
- Raw lesson: RPC service tasks pass when Wattle validates the exact protocol through generated client stubs and keeps the service alive after validation.

### `mailman`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `mailman__nhb67tc` configured `/etc/mailman3/mailman.cfg`, created `reading-group@local.edu`, generated Mailman command aliases, configured Postfix `main.cf` for `local.edu` local delivery and Mailman LMTP routing, set subscription/unsubscription policy, started services, and validated with `/app/eval.py`. The earlier pass `mailman__EPgf4zw` validated SMTP port 25, Mailman LMTP on `127.0.0.1:8024`, queue emptiness, and list settings.
- Oracle contrast: leaves a working Mailman/Postfix service integration with the expected list/domain aliases and local delivery behavior.
- Raw lesson: mail/service integration tasks pass when Wattle validates daemon liveness, generated routing maps, policy state, and the evaluator workflow together.

### `query-optimize`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `query-optimize__w54u8pV` saved `/app/sol.sql`, validated single-query/no-comments/semicolon formatting, executed successfully against `/app/oewn.sqlite`, returned 500 rows, and checked the same tested output hash as the optimized equivalent candidate. The earlier pass `query-optimize__SznDBb2` also validated identical output to the original query plus SQLite execution.
- Oracle contrast: preserves exact query results while improving the SQL plan and leaving a verifier-ready single SQL file.
- Raw lesson: query-optimization tasks pass when Wattle validates semantic equivalence against the original query and enforces final SQL formatting constraints.

### `code-from-image`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `code-from-image__p6tpuQf` wrote `/app/output.txt`; earlier pass `code-from-image__TuVgRiu` also wrote the expected 65-byte output artifact.
- Oracle contrast: extracts exact code/text content from the supplied image and writes only the verifier-expected output file.
- Raw lesson: image transcription tasks can pass when Wattle keeps the deliverable narrow and validates the exact output artifact rather than relying on descriptive interpretation.

### `fix-code-vulnerability`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `fix-code-vulnerability__PLUE5As` updated `/app/bottle.py` so response header names and values reject newline, carriage return, and NUL characters, wrote `/app/report.jsonl` with `cwe-93`, and validated `367 passed` through `pytest -rA`. Earlier pass `fix-code-vulnerability__Kbic8zY` used the same CWE-93 fix and report contract.
- Oracle contrast: patches the vulnerable header handling while preserving the existing Bottle test suite and producing the required vulnerability report.
- Raw lesson: security-fix tasks pass when Wattle pairs a minimal targeted validation with the full existing regression suite and exact report schema.

### `cancel-async-tasks`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `cancel-async-tasks__xbh8cLr` implemented importable `/app/run.py` with `run_tasks`, enforced `max_concurrent >= 1`, limited concurrency, and validated that cancelled tasks are awaited so cleanup/finally blocks run. Earlier pass `cancel-async-tasks__eDRkrfd` validated the same import, concurrency, and cancellation cleanup behavior.
- Oracle contrast: implements cancellation-safe async task orchestration using only the Python standard library.
- Raw lesson: async/concurrency tasks pass when Wattle validates behavioral invariants, especially cancellation cleanup, not only successful completion.

### `feal-differential-cryptanalysis`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `feal-differential-cryptanalysis__9eLKx5J` implemented `/app/attack.py` with `attack(encrypt_fn)`, recovered `key[5]`, validated 20 randomized key trials, and kept per-attack runtime around `0.20s`. Earlier pass validated 100 random keys and stayed under the 30-second budget.
- Oracle contrast: performs a chosen-plaintext differential attack and validates recovered key material against randomized FEAL keys.
- Raw lesson: cryptanalysis tasks pass when Wattle validates recovered secrets across many randomized keys under the verifier's runtime budget.

### `git-leak-recovery`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `git-leak-recovery__NDYYD3j` recovered the secret into `/app/secret.txt`, expired reflogs, pruned unreachable Git objects, validated no `secret[...]` pattern remained anywhere in `/app/repo`, confirmed reachable refs and object database were clean, and preserved unrelated repo content. Earlier pass `git-leak-recovery__KefH6Ny` validated unchanged `HEAD`, reachable commit messages, worktree status, no secret matches, and no dangling objects.
- Oracle contrast: recovers the secret while purging it from Git metadata without damaging the visible repository state.
- Raw lesson: Git forensics tasks pass when Wattle validates both recovery and complete metadata cleanup, including unreachable objects and state preservation.

### `build-cython-ext`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `build-cython-ext__TtASNXJ` cloned `pyknotid` 0.5.3 to `/app/pyknotid`, built and installed it into global Python with NumPy 2.3.0, verified the compiled extension modules import from global site-packages, and applied a NumPy >=2 compatibility shim for removed aliases. Earlier pass `build-cython-ext__vr64xLr` also patched Python/NumPy compatibility, built the Cython extensions, installed globally, preserved NumPy 2.3.0, and validated README/core-test behavior.
- Oracle contrast: clones the requested upstream tag, applies minimal compatibility edits for current Python/NumPy/Cython behavior, builds extensions in their original package context, and installs the package into the system environment.
- Raw lesson: dependency/build tasks pass when Wattle preserves the requested upstream version and package structure, validates from outside the checkout/global install path, and checks both extension loader type and end-user README behavior.

### `fix-ocaml-gc`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `fix-ocaml-gc__8g7uSCu` passed after the same root-cause fix as the earlier pass: change `pool_sweep` in `/app/ocaml/runtime/shared_heap.c` to advance through fixed-width sizeclass pool slots with `p += wh` rather than `p += Whsize_hd(hd)`, preserving the separate compressed-free-run skip. Earlier pass `fix-ocaml-gc__YBa6r5m` built the compiler and ran `make -C testsuite one DIR=tests/basic`.
- Oracle contrast: applies the targeted one-line slot-advance fix in `shared_heap.c`.
- Raw lesson: low-level runtime repair tasks pass when Wattle localizes the invariant violation, makes the smallest semantic fix, and validates through the exact requested build/test path rather than only compiling the touched file.

### `nginx-request-logging`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `nginx-request-logging__nTT8aiV` configured Nginx on localhost:8080, `/var/www/html`, `/etc/nginx/conf.d/benchmark-site.conf`, custom index/404 pages, benchmark access/error logs, quoted user-agent logging, rate limiting, and removed the default site; it syntax-tested/restarted Nginx and verified localhost/log creation. Earlier pass `nginx-request-logging__NKPwBRb` passed with the same service, logging, and custom-error-page contract.
- Oracle contrast: installs Nginx, adds the required `log_format` and `limit_req_zone` in `nginx.conf`, serves the expected static files on port 8080, writes logs to the exact benchmark paths, and leaves the service running.
- Raw lesson: web-service configuration tasks pass when Wattle validates exact config file locations, generated content, syntax, process liveness, reachable port, and log side effects together.

### `large-scale-text-editing`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `large-scale-text-editing__3roufBo` created `/app/apply_macros.vim`, ran `vim -Nu NONE -n -Es /app/input.csv -S /app/apply_macros.vim`, exited 0, byte-compared `/app/input.csv` against `/app/expected.csv`, and kept the script at 182 bytes with three distinct non-empty macros. Earlier pass `large-scale-text-editing__L9yicwK` used the same headless Vim command and `cmp` validation.
- Oracle contrast: defines three allowed Vim macros and applies them headlessly to transform the million-row CSV exactly.
- Raw lesson: large text-transformation tasks pass when Wattle validates the exact command surface and byte-for-byte final artifact, not just sampled rows or inferred transformations.

### `sqlite-db-truncate`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `sqlite-db-truncate__P5vJ3Xz` recovered readable rows from `/app/trunc.db`, wrote `/app/recover.json`, and validated that it is JSON with 10 `word`/`value` objects and numeric non-bool values. Earlier pass `sqlite-db-truncate__uWTDFf9` validated the same recovered-row count and schema.
- Oracle contrast: recovers rows directly from the truncated SQLite file bytes and emits the requested JSON artifact.
- Raw lesson: corrupted-data recovery tasks pass when Wattle validates the persisted recovery artifact by reloading it and checking schema/count/type constraints.

### `sanitize-git-repo`

- Status: both synced Wattle attempts passed, with an additional synced pass now visible.
- Current evidence: retry `sanitize-git-repo__QLsccgV` replaced AWS, GitHub, and Hugging Face secrets with the requested placeholders only in contaminated tracked files and validated no sensitive values remained. Earlier pass `sanitize-git-repo__r3Numch` made the same targeted replacements and scanned tracked files for all known secret literals.
- Oracle contrast: replaces only detected secret values with consistent placeholders while leaving uncontaminated files unchanged.
- Raw lesson: repository-sanitization tasks pass when Wattle combines broad secret scanning with an explicit changed-file scope audit and post-sanitization negative search.

### `build-pmars`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `build-pmars__VMbUdVQ` extracted Debian `pmars` source under `/app/pmars-0.9.4`, preserved Debian source artifacts, installed `/usr/local/bin/pmars`, built without X11 support, confirmed `ldd` had no X11 libraries, validated the requested battle output `Results: 12 30 8`, and passed debugger validation. Earlier pass `build-pmars__Wd2RSJt` used the same Debian-source/no-X11 path and validation.
- Oracle contrast: fetches Debian source rather than unreliable upstream, disables X11 graphing, installs the headless binary, and validates both battle output and debugger behavior.
- Raw lesson: native build tasks pass when Wattle validates provenance, dependency surface, install path, and the exact smoke command the verifier will exercise.

### `openssl-selfsigned-cert`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `openssl-selfsigned-cert__isvBRTM` created and verified `/app/ssl/server.key`, `/app/ssl/server.crt`, `/app/ssl/server.pem`, `/app/ssl/verification.txt`, and `/app/check_cert.py`, including 2048-bit RSA key, 365-day self-signed certificate, `DevOps Team` organization, `dev-internal.company.local` common name, SHA-256 fingerprint, key/PEM permissions, and script output. Earlier pass `openssl-selfsigned-cert__ZaCu7Vf` validated the same file set and metadata.
- Oracle contrast: uses OpenSSL commands to produce the exact certificate/key/combined-PEM artifacts, records certificate metadata, and leaves a verifier script that loads and reports the certificate.
- Raw lesson: cryptographic artifact tasks pass when Wattle validates file permissions, subject/validity/fingerprint metadata, combined artifact format, and the supplied verification script output.

### `vulnerable-secret`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `vulnerable-secret__TcZukxw` extracted the secret key, wrote `/app/results.txt`, and verified the file exactly equals `FLAG{b4ff3r_0v3rfl0w_m4st3r_k3y_2024}`. Earlier pass `vulnerable-secret__ryQwcnH` recovered the same secret into the same final artifact.
- Oracle contrast: extracts the hidden key and writes only the expected result artifact.
- Raw lesson: exploit/secret-recovery tasks pass when Wattle keeps the final deliverable narrow and validates the exact file content instead of leaving broader exploratory artifacts.

### `rstan-to-pystan`

- Status: both synced Wattle attempts passed.
- Current evidence: retry `rstan-to-pystan__eaDhx9s` completed PyStan posterior sampling with exit code 0 and produced the required `/app/alpha_est.csv`, `/app/sigma_est.csv`, `/app/rho_est.csv`, and `/app/beta_est.csv` files with the expected row counts. Earlier pass `rstan-to-pystan__TVwE9vy` installed PyStan 3.10.0, created `/app/pystan_analysis.py`, used `stan.build(..., random_seed=1)` with RStan-equivalent sampling settings, and validated numeric-only outputs.
- Oracle contrast: translates the RStan model and sampling hyperparameters to PyStan 3 while preserving model semantics, seed, posterior summaries, and CSV output schema.
- Raw lesson: probabilistic-model translation tasks pass when Wattle preserves library-specific sampling semantics and validates persisted posterior summary files after the long run completes.

### `llm-inference-batching-scheduler`

- Status: all synced Wattle attempts passed.
- Current evidence: retry `llm-inference-batching-scheduler__tfEmF5Y` generated `/app/task_file/output_data/plan_b1.jsonl` and `plan_b2.jsonl`, then validated exact request coverage, no duplicate IDs, batch-shape consistency, cost, padding ratio, p95 latency, and sequential timecost against `/app/task_file/scripts/cost_model.py`. Earlier passes `llm-inference-batching-scheduler__kbZUPgH` and `llm-inference-batching-scheduler__kgrrhCE` used the same metric-driven validation approach.
- Oracle contrast: batches requests into valid plans that optimize cost/latency/padding metrics while preserving exact request coverage and shape constraints.
- Raw lesson: optimization-planning tasks pass when Wattle uses the official cost model as the validation oracle and checks every hard constraint plus objective threshold before finalizing.

## Running Or Incomplete At Snapshot

### `path-tracing` retry

- Status: Wattle retry `path-tracing__fp6agpu` is running.
- Current evidence: prior completed attempts passed after writing compact `/app/image.c`, compiling it, generating `reconstructed.ppm`, staying under the 2k compressed-source limit, validating dimensions, and checking high image similarity. The running retry is fitting camera, checker plane, sphere, and lighting parameters from pixel samples before implementing a compact `image.c` and validating with an independent similarity script.
- Watch point: if the retry passes, keep this as positive evidence for combining compact source-size checks with independent image-similarity validation.
- Do not classify the retry outcome yet. It should be analyzed after a completed `result.json` is synced.

### `regex-chess` retry

- Status: Wattle retry `regex-chess__Zv766pg` is running.
- Current evidence: prior completed attempts passed after generating `/app/re.json` within size and pair-count limits, matching the sample output, passing `/app/check.py`, and validating special move cases against `python-chess`. The running retry has inspected checker behavior and is generating regex rules that expand FEN, emit candidate next positions, filter illegal king-in-check positions, and recompress; it is now running broader randomized validation on valid game-reachable white-to-move positions plus constructed special positions.
- Watch point: if the retry passes, keep this as positive evidence for using an executable reference model to generate compact regex-rewrite artifacts under strict file constraints.
- Do not classify the retry outcome yet. It should be analyzed after a completed `result.json` is synced.
