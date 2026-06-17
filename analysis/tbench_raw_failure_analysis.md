# Terminal-Bench 2.0 Raw Failure Analysis

Generated from the GCP amd64 Wattle run `wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616`.

Snapshot used: `2026-06-17T06:25:17Z`

Counts at snapshot:

- Passed: 85
- Failed: 26
- Exceptions: 8
- Running or incomplete: 2
- Prompt-cache hit rate: 85.4%

Deep evidence reports were regenerated under:

```text
runs/gcp/wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616/analysis/failure_analysis/tasks/
```

The Codex comparison run `codex-compare-nonpassed-20260617` had fourteen completed comparisons at this snapshot: Codex passed `build-pov-ray`, `db-wal-recovery`, `extract-moves-from-video`, `gpt2-codegolf`, and `mteb-retrieve`; failed `configure-git-webserver`, `install-windows-3.11`, `overfull-hbox`, `polyglot-rust-c`, `torch-tensor-parallelism`, `train-fasttext`, and `video-processing`; and timed out on `caffe-cifar-10` and `make-doom-for-mips`. Codex `gcode-to-text` was running. Most task notes remain grounded in Wattle logs, verifier failures, and Terminal-Bench oracle/tests.

## Confirmed Failures And Exceptions

### `build-pov-ray`

- Status: failed.
- Verifier: expected POV-Ray 2.2 source marker `file_id.diz`; it was missing, indicating the wrong extraction/build layout or wrong source version.
- Oracle contrast: downloads the exact `Official-2.2` `POVDOC`, `POVSCN`, and `POVSRC` archives, extracts them in `/app`, copies `machine/unix/*` into `source`, patches build files, and installs the resulting binary.
- Wattle behavior: reported a successful build and render but left the source tree in a layout the verifier considered wrong.
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

- Status: failed.
- Verifier: `primers.fasta` existed and had the expected primer inventory, but at least one forward/reverse pair had an annealing Tm delta of 5.071125 C, just above the allowed 5 C threshold.
- Oracle contrast: chooses exact template cut boundaries, excludes insert start/stop codons where required, derives Golden Gate overhangs from the verifier-equivalent reverse-complement reconstruction, and validates every annealing tract with `oligotm -tp 1 -sc 1 -mv 50 -dv 2 -n 0.8 -d 500`.
- Wattle behavior: did substantial correct setup work and reported that all forward/reverse Tm differences were within 5 C, but its final local validation did not match the verifier closely enough near the threshold.
- Raw lesson: near-threshold scientific/design tasks need verifier-equivalent reconstruction with margin; Wattle should not accept a final design where an exact hidden check can fail by a small tolerance.

### `dna-insert`

- Status: failed.
- Verifier: `primers.fasta` existed and encoded the insert, but the forward and reverse annealing Tm values differed by 6.531905 C, above the allowed 5 C.
- Oracle contrast: computes the reverse annealing segment in the primer/verifier orientation with `oligotm -tp 1 -sc 1 -mv 50 -dv 2 -n 0.8 -d 500`, writes exactly one forward/reverse pair, and validates the reconstructed `rc(reverse_primer) + forward_primer` insert plus vector overlaps.
- Wattle behavior: wrote a plausible one-pair FASTA and locally reported a 0.074115 C Tm difference, but its local check used the reverse annealing sequence orientation differently from the verifier.
- Raw lesson: scientific/design tasks need verifier-equivalent reconstruction and orientation checks, not only domain-plausible local validation.

### `extract-elf`

- Status: failed.
- Verifier: only 0% of expected values matched.
- Oracle contrast: parses ELF headers, sections, symbol tables, memory words, function symbols, and address/function mappings using a full ELF parser.
- Wattle behavior: emitted valid JSON with plausible numeric keys, but the data model did not match the expected ELF extraction contract.
- Raw lesson: for binary formats, superficial output schema checks are insufficient; Wattle needs contract-derived structural checks against known sections/symbols.

### `extract-moves-from-video`

- Status: failed.
- Verifier: solution text similarity was 63.37%, below the 90% threshold.
- Oracle contrast: derives the Zork command transcript from the video rather than producing a merely plausible command list.
- Wattle behavior: wrote a syntactically clean `solution.txt`, but the extracted sequence was materially different.
- Codex comparison: Codex passed this task, so the failure points to Wattle's video/transcript extraction strategy rather than a task or harness issue.
- Raw lesson: media/OCR tasks need confidence-aware extraction and cross-validation, not just format validation.

### `filter-js-from-html`

- Status: failed.
- Verifier: missed XSS vectors and modified 5 clean HTML files.
- Oracle contrast: uses BeautifulSoup to remove dangerous tags and attributes while preserving benign structure.
- Wattle behavior: validated a narrow sample but did not exercise the task's clean-preservation and adversarial-vector contract.
- Raw lesson: when a task implies a filter/sanitizer, Wattle should build and run a representative adversarial and clean regression set before finalizing.

### `financial-document-processor`

- Status: exception, `NonZeroAgentExitCodeError`.
- Verifier: invoices and `summary.csv` were missing or incomplete.
- Oracle contrast: implements OCR/text extraction for images/PDFs, content-based invoice classification, moves every document, and writes a structured invoice summary.
- Wattle behavior: began moving a hand-classified subset and then exited before completing destination directories and summary output.
- Raw lesson: multi-file classification tasks need transaction-style staging: classify all files, validate total coverage, then move/write outputs atomically.

### `gcode-to-text`

- Status: failed.
- Verifier: expected `flag{gc0d3_iz_ch4LLenGiNg}`, got `the quick brown fox jumps over the lazy dog`.
- Oracle contrast: renders rotated 3D G-code segments and uses image/OCR tooling to recover the hidden text.
- Wattle behavior: solved for a visually plausible decoded sentence, but not the verifier target.
- Raw lesson: Wattle should avoid accepting first plausible OCR/vision output without checking task-specific hidden-message criteria and alternative views.

### `gpt2-codegolf`

- Status: failed.
- Verifier: `gpt2.c` did not satisfy the full compile/run contract.
- Oracle contrast: provides a dense under-5000-byte GPT-2 implementation with the exact expected CLI and checkpoint/vocab reading behavior.
- Wattle behavior: created small C implementations and smoke-tested them, but both Wattle trials failed the verifier; the retry had size/compile checks passing and then failed the semantic expected-continuation check for a known verifier prompt.
- Codex comparison: Codex passed the same task in the comparison run, which suggests the harness/task is healthy and Wattle's miss is in exact contract execution rather than environment setup.
- Raw lesson: code-golf/implementation tasks need verifier-like command reproduction and semantic output checks, including exact file path, argv, size, compile flags, tokenization, checkpoint layout, BPE mapping, and expected continuation contract.

### `install-windows-3.11`

- Status: exception, `NonZeroAgentExitCodeError`.
- Verifier: QEMU was not running and VNC port 5901 was not listening.
- Oracle contrast: compiles/uses QEMU 5.2.0, starts the Windows image with the required legacy device flags, VNC `:1`, nginx/noVNC service, and monitor interfaces.
- Wattle behavior: investigated boot flags but did not leave the required long-running VM services alive.
- Codex comparison: Codex also failed the verifier, with QEMU running against `/app/win311-runtime.img` instead of the expected `/app/isos/win311.img`, plus visual-feedback key tests failing.
- Raw lesson: service tasks need a final liveness gate for all required processes/ports after any debugging restarts.

### `make-doom-for-mips`

- Status: exception, `AgentTimeoutError`.
- Verifier: no final passing result before timeout.
- Oracle contrast: applies a large MIPS build patch, supplies custom libc/runtime pieces, cross-compiles, and validates under the JS VM.
- Wattle behavior: built a MIPS binary and generated a frame, but execution stopped on an unsupported instruction before reaching a stable verifier-ready state.
- Codex comparison: Codex also timed out. Its verifier output reached Doom initialization but still missed the expected graphics initialization text `I_InitGraphics: DOOM screen size: w x h: 320 x 200`.
- Raw lesson: emulator/cross-compile tasks need early ISA/runtime compatibility checks and a plan to minimize late-cycle debugging.

### `mcmc-sampling-stan`

- Status: exception, `AgentTimeoutError`.
- Verifier: posterior alpha and beta means were astronomically wrong relative to expected ranges, despite Wattle reporting plausible mean files before timeout.
- Oracle contrast: installs pinned RStan dependencies, uses a hierarchical binomial Stan model with the intended prior transformation, then runs a long reproducible sample to write posterior means.
- Wattle behavior: generated the required files and an apparently good intermediate result, then changed the Stan model/rerun path and timed out with verifier-visible bad posterior files.
- Raw lesson: probabilistic/scientific tasks need stable final artifact protection; once a verifier-plausible result is produced, later experiments should not overwrite it without passing the same checks.

### `model-extraction-relu-logits`

- Status: failed.
- Verifier: `stolen_A1.npy` existed, but row 11 of the verifier's original 30x10 matrix could not be matched up to scaling.
- Oracle contrast: uses query-only ReLU critical-point sweeps that are robust to unknown hidden width and verifier-generated weights.
- Wattle behavior: produced a script and locally validated perfect recovery against the visible `/app/forward.py` internals, including a visible 20x10 `A1`, but the verifier used a different generated matrix and exposed incomplete row recovery.
- Raw lesson: model-extraction tasks need hidden-input robustness checks and should not rely on visible implementation constants as proof of correctness; validation should test generality over shape/seed variations where possible.

### `mteb-leaderboard`

- Status: failed.
- Verifier: expected `GritLM/GritLM-7B`; Wattle wrote `Salesforce/SFR-Embedding-2_R`.
- Oracle contrast: checks out the MTEB results repo at a specific commit, loads the exact `MTEB(Scandinavian, v1)` benchmark, filters models with all tasks, and computes complete-task averages.
- Wattle behavior: selected a plausible leaderboard winner but did not reproduce the exact dated result computation.
- Raw lesson: benchmark/leaderboard tasks require exact dataset snapshot, benchmark name, completeness filters, and aggregation semantics.

### `mteb-retrieve`

- Status: failed in both synced Wattle attempts.
- Verifier: expected `MTEB: Massive Text Embedding Benchmark`; Wattle wrote `HumanEval: Benchmarking Python code generation via functional examples`.
- Oracle contrast: uses `mteb.get_model("BAAI/bge-small-zh-v1.5", revision=...)`, encodes query with `task_name="SciFact"` and `PromptType.query`, encodes docs with `PromptType.passage`, then selects the 5th highest similarity.
- Wattle behavior: inspected model/wrapper details but still wrote the wrong document in both attempts; retry `mteb-retrieve__Mr7e9Et` also synced the same unexpected result.
- Codex comparison: Codex passed this task in the comparison run, which reinforces that the failure is not the harness or task image but Wattle's exact MTEB API/revision/prompt-type/ranking reproduction.
- Raw lesson: embedding tasks are sensitive to wrapper semantics, prompt type, task name, revision, and ranking convention; Wattle needs exact API parity with the prompt/oracle.

### `overfull-hbox`

- Status: failed.
- Verifier: modified `input.tex` using `veteran`, which was not an allowed synonym replacement for `old`.
- Oracle contrast: parses `main.log`, builds substitutions only from `synonyms.txt`, repeatedly compiles and substitutes one allowed synonym until no overfull boxes remain.
- Wattle behavior: achieved no overfull hbox warnings, but violated the allowed-edit contract.
- Codex comparison: Codex also failed this task with the same allowed-edit contract pattern, replacing `old` with `veteran` even though that synonym was not present in `synonyms.txt`.
- Raw lesson: validation should check both the desired effect and the permitted transformation set.

### `polyglot-c-py`

- Status: failed.
- Verifier: expected only `main.py.c`; found an extra `cmain`.
- Oracle contrast: creates only `polyglot/main.py.c`; compiled binaries are not left in the target directory.
- Wattle behavior: created the correct source and validated it, but left build artifacts in the directory the verifier checks.
- Raw lesson: Wattle needs cleanup/final-state hygiene after validation, especially in tasks with exact directory contents.

### `polyglot-rust-c`

- Status: failed.
- Verifier: expected only `main.rs`; found `main`, `cmain`, and `main.rs`.
- Oracle contrast: creates only `polyglot/main.rs`; build products are not left in place.
- Wattle behavior: validated both Rust and C++ compilation but left generated executables/symlinks.
- Codex comparison: Codex also failed the task with the same final-inventory contract class, leaving `main` beside `main.rs`. That makes the failure pattern broader than Wattle-specific execution cleanup.
- Raw lesson: exact output inventories should be treated as part of the task contract, not incidental filesystem state.

### `protein-assembly`

- Status: failed.
- Verifier: fusion protein order was wrong; expected flag, donor, DHFR, acceptor, SNAP.
- Oracle contrast: identifies binder/tag semantics, resolves SNAP/fluorescent protein choices from external sequence sources, then assembles the sequence in the specified order.
- Wattle behavior: generated a valid DNA-looking `gblock.txt`, but the translated protein did not satisfy component ordering.
- Raw lesson: bio/design tasks need semantic validation against named components and ordering, not only sequence validity.

### `pytorch-model-recovery`

- Status: failed.
- Verifier: TorchScript `forward()` expected at most 2 arguments but received 3; the expected recovered model interface accepts source and target tensors.
- Oracle contrast: reconstructs the transformer-style architecture from `weights.pt`, including `forward(self, src, tgt)`, tunes only `output_layer`, then saves `/app/model.pt` as TorchScript.
- Wattle behavior: produced a TorchScript model with a single-input forward signature, so it could not be called by the verifier's dataset path.
- Raw lesson: model-recovery tasks need exact module interface validation, not only state-dict loading and local loss checks.

### `raman-fitting`

- Status: failed.
- Verifier: fitted G and 2D peak parameters were far from expected values.
- Oracle contrast: converts decimal commas/tab format, converts wavelength nm to cm^-1, crops G and 2D peak regions, then fits Lorentzian peaks with SciPy.
- Wattle behavior: produced JSON with fit parameters, but likely used the wrong x-axis transformation/crop/model setup.
- Raw lesson: numerical science tasks need unit conversion and range checks before fitting; output plausibility is not enough.

### `sam-cell-seg`

- Status: failed.
- Verifier: eight tests passed, including script execution, CSV shape, non-rectangular masks, alignment, non-overlap, and single-contiguous-mask checks. The only failure was `test_coords_are_flat_lists`: row 0 `coords_x` parsed as a tuple instead of a list.
- Oracle contrast: uses MobileSAM box prompts, resolves overlaps/contiguity, then writes `coords_x` and `coords_y` as flat list-like fields accepted by the verifier.
- Wattle behavior: solved the substantive segmentation geometry but missed the exact CSV serialization contract for coordinate columns.
- Raw lesson: Wattle needs final output-type/schema validation at the serialized artifact level, not just in-memory data structure validation.

### `torch-tensor-parallelism`

- Status: failed.
- Verifier: gradient mismatch for both column and row parallel linear layers.
- Oracle contrast: implements Megatron-style autograd collectives: copy input forward/all-reduce gradient backward, gather output forward/split gradient backward, reduce output forward/identity backward.
- Wattle behavior: passed basic syntax/forward-style checks but failed distributed gradient semantics.
- Codex comparison: Codex also failed this task, with row-parallel failures across multi-rank cases. This reinforces that the task requires exact distributed autograd semantics, not just Wattle-specific cleanup.
- Raw lesson: framework tasks need backward-pass tests and multi-rank numerical equivalence, not only import/forward smoke tests.

### `train-fasttext`

- Status: exception, `AgentTimeoutError`.
- Verifier: private accuracy was 0.539925, below threshold 0.62.
- Oracle contrast: converts the provided parquet train set to FastText supervised format and trains with `wordNgrams 2` and `dim 5`.
- Wattle behavior: reported acceptable validation on its own processed split, but verifier used the real private evaluation contract and failed.
- Codex comparison: Codex also failed, with private accuracy 0.58465 below the same 0.62 threshold. This makes the issue broader than Wattle-only execution and reinforces the need for exact data conversion/training settings and validation with margin.
- Raw lesson: ML tasks need validation that matches the verifier input format and threshold with margin; internal split success can be misleading.

### `video-processing`

- Status: failed.
- Verifier: landing frame was 230; expected inclusive range 231 to 234.
- Oracle contrast: uses frame-level movement/background subtraction and task-specific thresholds to locate jump start/end.
- Wattle behavior: got very close but failed an off-by-one/tolerance-sensitive boundary.
- Codex comparison: Codex also failed a tight boundary check, but on takeoff rather than landing: takeoff frame 226 was outside the inclusive range 219 to 223.
- Raw lesson: video/temporal tasks need exact boundary calibration and verifier-range checks before final answer.

## Completed Passing Retries Since Prior Snapshot

### `break-filter-js-from-html`

- Status: passed in both synced Wattle attempts.
- Current evidence: the retry `break-filter-js-from-html__wwLsocx` completed successfully after crafting `/app/out.html` that survives the provided filter and still triggers an automatic Chromium `alert(1)`.
- Oracle contrast: uses a malformed HTML comment that the filter mishandles but Chromium still parses into executable script.
- Raw lesson: this remains a positive example for parser-differential adversarial validation; it does not change the general failure taxonomy.

### `write-compressor`

- Status: passed in both synced Wattle attempts.
- Current evidence: the retry `write-compressor__kXTZ9Z9` completed successfully after producing `/app/data.comp` at 2280 bytes and validating that `cat data.comp | /app/decomp` exactly matches `/app/data.txt`. The earlier pass produced a 2476-byte `data.comp`.
- Oracle contrast: reverse-engineers the decompressor format and emits a compact compressed stream below the 2500-byte limit.
- Raw lesson: this remains a positive example for exact executable-output validation against a strict size budget; it does not change the general failure taxonomy.

### `reshard-c4-data`

- Status: passed in both synced Wattle attempts.
- Current evidence: the retry `reshard-c4-data__WYFJgZy` completed successfully after passing focused validation: `uv sync`, syntax checks, CLI help checks, full `c4_sample` round-trip, directory entry and file-size limits, `diff -qr`, and an edge-case round-trip preserving `.reshard_*`-named original paths.
- Oracle contrast: writes `compress.py`, `decompress.py`, `pyproject.toml`, and uv metadata so the archive can be compressed and then reconstructed exactly in-place under the task's directory and file-size constraints.
- Raw lesson: this remains a positive example for verifier-like artifact and round-trip validation under filesystem constraints; it does not change the general failure taxonomy.

### `merge-diff-arc-agi-task`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `merge-diff-arc-agi-task__6XScxMA` completed successfully after initializing `/app/repo`, fetching both bundles into `branch1` and `branch2`, merging, resolving `algo.py`, and validating all examples. The earlier attempt `merge-diff-arc-agi-task__ofUGtxY` also passed with the same branch setup and example validation.
- Oracle contrast: creates `branch1` and `branch2` from the bundles, uses branch1 as base, applies the branch2 state, then implements `algo.py` with a modulo-diagonal color mapping inferred from examples.
- Raw lesson: this remains a positive example for exact repository-state setup plus verifier-like example validation; it does not change the general failure taxonomy.

### `pytorch-model-cli`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `pytorch-model-cli__Ppsm6C6` completed successfully after creating `/app/cli_tool`, `/app/weights.json`, and `/app/prediction.txt`, validating that `./cli_tool weights.json image.png` outputs only `2`, confirming `prediction.txt` contains only `2`, and checking that `/app/cli_tool` is an ELF executable. The earlier attempt `pytorch-model-cli__j8TEW5F` passed with the same exact CLI/output contract.
- Oracle contrast: builds a CLI around the supplied image/model assets, writes the expected prediction artifact, and preserves the exact command interface.
- Raw lesson: this remains a positive example for exact final command and artifact validation; it does not change the general failure taxonomy.

### `largest-eigenval`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `largest-eigenval__Vd5wSwF` completed successfully after implementing `/app/eigen.py` with NumPy's LAPACK-backed private eigen ufunc, selecting the dominant eigenvalue by magnitude, returning the corresponding right eigenvector, and validating `/app/eval.py` correctness and speed against the reference. The earlier pass `largest-eigenval__A5bGYJK` used the same lower-overhead LAPACK path plus exact 1x1 and 2x2 fast paths.
- Oracle contrast: implements the dominant eigenpair function with exact correctness and performance constraints against the evaluation harness.
- Raw lesson: this remains a positive example for pairing performance optimization with verifier-like correctness checks across matrix sizes; it does not change the general failure taxonomy.

### `portfolio-optimization`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `portfolio-optimization__3N3WX9B` completed successfully after implementing C-backed `portfolio_risk_c` and `portfolio_return_c`, converting Python inputs to contiguous NumPy `float64` arrays, preserving the public wrapper API, building the extension, and validating with `benchmark.py`. The earlier pass `portfolio-optimization__e5C3zxs` used the same C-backed risk/return implementation and validation path.
- Oracle contrast: implements fast C-backed portfolio risk and return functions while preserving the exact Python wrapper contract and benchmark correctness.
- Raw lesson: this remains a positive example for exact wrapper-preserving optimization plus benchmark validation; it does not change the general failure taxonomy.

### `path-tracing-reverse`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `path-tracing-reverse__PfxM9GJ` completed successfully after writing standalone `/app/mystery.c`, compiling it with `gcc -static -o reversed mystery.c -lm`, confirming generated `image.ppm` matched the original output byte-for-byte, confirming the SHA256, and keeping compressed source size under 2k. The earlier pass `path-tracing-reverse__K2cVozH` used the same byte-for-byte image and stderr/progress validation.
- Oracle contrast: reconstructs a compact C renderer that reproduces the hidden path-tracing output and progress behavior under the compressed-size constraint.
- Raw lesson: this remains a positive example for exact behavioral reproduction plus compressed-source validation; it does not change the general failure taxonomy.

### `path-tracing`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `path-tracing__dhCWrsR` completed successfully after writing `/app/image.c`, compiling it, generating `reconstructed.ppm`, keeping compressed source at `3 19 644` from `cat image.c | gzip | wc`, validating output dimensions `2400x1800`, and reaching local relative-L2-style similarity `0.9929`. The earlier pass `path-tracing__iZaeUpX` also generated `/app/reconstructed.ppm`, stayed under 2k compressed, and reached high normalized-L2 similarity.
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

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `regex-chess__e3gJsr6` completed successfully after writing `/app/re.json` as a JSON list of regex/replacement pairs, validating the sample output, passing `/app/check.py`, satisfying the pair-count and size limits, and passing additional valid-position comparisons against `python-chess` for castling, queen promotion, and en-passant cases. The earlier pass `regex-chess__eBbYn7d` generated 6,863 pairs and passed the same checker.
- Oracle contrast: generates a regex/pattern inventory that makes the chess PGN checker pass while preserving the exact JSON interface expected by the tests.
- Raw lesson: this remains a positive example for matching the verifier's normalization contract and then broadening validation over legal edge cases; it does not change the general failure taxonomy.

### `modernize-scientific-stack`

- Status: passed in both synced Wattle attempts.
- Current evidence: retry `modernize-scientific-stack__mWcAi6j` completed successfully after creating `/app/analyze_climate_modern.py` and `/app/requirements.txt`, preserving the same data/config inputs, running the script, and validating the expected station mean-temperature output. The earlier pass `modernize-scientific-stack__wrSjEGR` also compile-checked the modern script and preserved the legacy `/app/climate_analyzer/analyze_climate.py`.
- Oracle contrast: modernizes the scientific stack while preserving the same data/config behavior and expected output without modifying the legacy file.
- Raw lesson: this remains a positive example for preserving legacy behavior while modernizing dependencies and syntax; it does not change the general failure taxonomy.

### `torch-tensor-parallelism` retry

- Status: passed after an earlier Wattle failure.
- Current evidence: retry `torch-tensor-parallelism__DJJCv6Q` completed successfully after implementing `/app/parallel_linear.py` with sharded column/row parallel layers plus custom autograd wrappers for gather/reduce behavior so local weight and bias gradients are preserved. The earlier Wattle attempt failed gradient checks, and Codex also failed row-parallel indexing/shape behavior.
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

- Status: exception, `AgentTimeoutError`, after another Wattle attempt passed.
- Current evidence: one Wattle attempt for this task already passed with verifier-style `pmars -b -r 100 -f` validation above all required win thresholds. Retry `winning-avg-corewars__KJ5akir` timed out after a bounded search; its final state left an early placeholder/test `my_warrior.red` that the verifier scored at 0% against `stone.red`, while the best temporary candidate still missed the `snake` and `g2-clear` thresholds.
- Oracle contrast: writes a multi-component Redcode warrior and validates against stone, vampire, paper, snake, and G2-Clear without modifying opponent files.
- Raw lesson: when search does not find a fully validated candidate before timeout, Wattle should not leave placeholder/test artifacts as the verifier-visible final answer. It should either preserve the best fully validated deliverable or clearly fail without an invalid placeholder.

### `pypi-server`

- Status: one Wattle attempt failed and one retry passed.
- Current evidence: failed attempt `pypi-server__5YR7FXj` produced a wheel and local simple index and locally validated `pip install`, but the verifier's `pip install --index-url http://localhost:8080/simple vectorops==0.1.0` returned non-zero. Retry `pypi-server__HoQwWjN` passed after using a `src/vectorops` package layout, placing the wheel under `pypi/simple/vectorops/`, and validating the server on port 8080.
- Oracle contrast: serves a PyPI-compatible simple index on port 8080 with the expected package/version/function import contract.
- Raw lesson: package-index tasks need verifier-exact index layout and install command validation, not only a local package build or manually tested alternate layout.

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

## Running Or Incomplete At Snapshot

### `overfull-hbox` retry

- Status: Wattle retry `overfull-hbox__iv3p9dd` is running.
- Current evidence: two prior Wattle attempts failed because `input.tex` used words outside the allowed `synonyms.txt` edit set even though the TeX output itself avoided overfull boxes. Codex also failed this comparison with the same allowed-edit contract miss.
- Watch point: if the retry passes, compare whether it introduced an explicit allowed-synonym audit before finalizing.
- Do not classify the retry outcome yet. It should be analyzed after a completed `result.json` is synced.

### `polyglot-rust-c` retry

- Status: Wattle retry `polyglot-rust-c__ciAfnzW` is running.
- Current evidence: two prior Wattle attempts failed because compiled artifacts such as `main` and `cmain` remained beside `main.rs`, while the verifier expected only `main.rs`. Codex also failed this comparison by leaving an extra `main`.
- Watch point: if the retry passes, compare whether it moved validation artifacts outside the checked directory or cleaned them before final validation.
- Do not classify the retry outcome yet. It should be analyzed after a completed `result.json` is synced.

### Codex `gcode-to-text` comparison

- Status: Codex comparison `gcode-to-text__Den56ri` is running.
- Current evidence: Wattle decoded a plausible sentence, `the quick brown fox jumps over the lazy dog`, but the verifier expected `flag{gc0d3_iz_ch4LLenGiNg}`. The oracle renders rotated G-code segments and applies image/OCR tooling to recover the hidden text.
- Watch point: if Codex passes, compare its view-selection/rendering/OCR workflow to Wattle's first-plausible-output behavior; if it fails, this reinforces the need for stronger media extraction confidence checks.
- Do not classify the Codex comparison outcome yet. It should be analyzed after a completed `result.json` is synced.
