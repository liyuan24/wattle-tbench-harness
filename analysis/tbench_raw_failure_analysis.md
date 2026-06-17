# Terminal-Bench 2.0 Raw Failure Analysis

Generated from the GCP amd64 Wattle run `wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616`.

Snapshot used: `2026-06-17T03:46:38Z`

Counts at snapshot:

- Passed: 50
- Failed: 18
- Exceptions: 6
- Running or incomplete: 2
- Prompt-cache hit rate: 86.4%

Deep evidence reports were regenerated under:

```text
runs/gcp/wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616/analysis/failure_analysis/tasks/
```

The Codex comparison run `codex-compare-nonpassed-20260617` had two completed comparisons at this snapshot: Codex passed `gpt2-codegolf` and failed `torch-tensor-parallelism`. `caffe-cifar-10` was still running. Most task notes remain grounded in Wattle logs, verifier failures, and Terminal-Bench oracle/tests.

## Confirmed Failures And Exceptions

### `build-pov-ray`

- Status: failed.
- Verifier: expected POV-Ray 2.2 source marker `file_id.diz`; it was missing, indicating the wrong extraction/build layout or wrong source version.
- Oracle contrast: downloads the exact `Official-2.2` `POVDOC`, `POVSCN`, and `POVSRC` archives, extracts them in `/app`, copies `machine/unix/*` into `source`, patches build files, and installs the resulting binary.
- Wattle behavior: reported a successful build and render but left the source tree in a layout the verifier considered wrong.
- Raw lesson: Wattle validated executable behavior without validating the verifier-visible provenance and required source artifacts.

### `caffe-cifar-10`

- Status: exception, `AgentTimeoutError`.
- Verifier: expected `/app/caffe/examples/cifar10/cifar10_quick_iter_500.caffemodel` and `/app/caffe/training_output.txt`; neither existed.
- Oracle contrast: installs Caffe dependencies, checks out BVLC Caffe at `9b89154`, applies CPU/OpenCV/HDF5 compatibility patches, builds Caffe, runs CIFAR data prep, then runs exactly 500 iterations with output tee'd to `training_output.txt`.
- Wattle behavior: spent the budget on setup/training attempts but did not complete the required model and output artifact.
- Raw lesson: long build/train tasks need earlier task-plan compression, deadline-aware fallbacks, and explicit artifact checkpoints before continuing expensive work.

### `configure-git-webserver`

- Status: failed.
- Verifier: after its own clone/push/curl flow, the web server returned HTTP 404.
- Oracle contrast: creates a bare repo at `/git/server`, deploys via `post-receive` to `/var/www/html`, and serves that root on port 8080.
- Wattle behavior: validated a manual flow, then reset repo/web-root state so the verifier's fresh workflow did not see `hello.html`.
- Raw lesson: Wattle should preserve the final state required by the verifier, not reset after a smoke test unless the instruction explicitly requires reset.

### `db-wal-recovery`

- Status: failed.
- Verifier: `Apple` stayed at value `100`; expected WAL update value `150`, proving encrypted WAL changes were not applied.
- Oracle contrast: detects the XOR-encrypted WAL, XOR-decrypts it with key `0x42`, replaces `/app/main.db-wal`, then lets SQLite apply the WAL before writing `recovered.json`.
- Wattle behavior: produced valid-looking JSON with rows sorted by id, but from the base database state rather than recovered WAL state.
- Raw lesson: Wattle should treat sidecar recovery files as first-class input and verify semantic deltas, not only output shape.

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
- Wattle behavior: created a small C implementation and smoke-tested it, but the verifier still rejected the implementation contract.
- Codex comparison: Codex passed the same task in the comparison run, which suggests the harness/task is healthy and Wattle's miss is in exact contract execution rather than environment setup.
- Raw lesson: code-golf/implementation tasks need verifier-like command reproduction, including exact file path, argv, size, compile flags, and output contract.

### `install-windows-3.11`

- Status: exception, `NonZeroAgentExitCodeError`.
- Verifier: QEMU was not running and VNC port 5901 was not listening.
- Oracle contrast: compiles/uses QEMU 5.2.0, starts the Windows image with the required legacy device flags, VNC `:1`, nginx/noVNC service, and monitor interfaces.
- Wattle behavior: investigated boot flags but did not leave the required long-running VM services alive.
- Raw lesson: service tasks need a final liveness gate for all required processes/ports after any debugging restarts.

### `make-doom-for-mips`

- Status: exception, `AgentTimeoutError`.
- Verifier: no final passing result before timeout.
- Oracle contrast: applies a large MIPS build patch, supplies custom libc/runtime pieces, cross-compiles, and validates under the JS VM.
- Wattle behavior: built a MIPS binary and generated a frame, but execution stopped on an unsupported instruction before reaching a stable verifier-ready state.
- Raw lesson: emulator/cross-compile tasks need early ISA/runtime compatibility checks and a plan to minimize late-cycle debugging.

### `mcmc-sampling-stan`

- Status: exception, `AgentTimeoutError`.
- Verifier: posterior alpha and beta means were astronomically wrong relative to expected ranges, despite Wattle reporting plausible mean files before timeout.
- Oracle contrast: installs pinned RStan dependencies, uses a hierarchical binomial Stan model with the intended prior transformation, then runs a long reproducible sample to write posterior means.
- Wattle behavior: generated the required files and an apparently good intermediate result, then changed the Stan model/rerun path and timed out with verifier-visible bad posterior files.
- Raw lesson: probabilistic/scientific tasks need stable final artifact protection; once a verifier-plausible result is produced, later experiments should not overwrite it without passing the same checks.

### `mteb-leaderboard`

- Status: failed.
- Verifier: expected `GritLM/GritLM-7B`; Wattle wrote `Salesforce/SFR-Embedding-2_R`.
- Oracle contrast: checks out the MTEB results repo at a specific commit, loads the exact `MTEB(Scandinavian, v1)` benchmark, filters models with all tasks, and computes complete-task averages.
- Wattle behavior: selected a plausible leaderboard winner but did not reproduce the exact dated result computation.
- Raw lesson: benchmark/leaderboard tasks require exact dataset snapshot, benchmark name, completeness filters, and aggregation semantics.

### `mteb-retrieve`

- Status: failed.
- Verifier: expected `MTEB: Massive Text Embedding Benchmark`; Wattle wrote `HumanEval: Benchmarking Python code generation via functional examples`.
- Oracle contrast: uses `mteb.get_model("BAAI/bge-small-zh-v1.5", revision=...)`, encodes query with `task_name="SciFact"` and `PromptType.query`, encodes docs with `PromptType.passage`, then selects the 5th highest similarity.
- Wattle behavior: inspected model/wrapper details but still wrote the wrong document.
- Raw lesson: embedding tasks are sensitive to wrapper semantics, prompt type, task name, revision, and ranking convention; Wattle needs exact API parity with the prompt/oracle.

### `overfull-hbox`

- Status: failed.
- Verifier: modified `input.tex` using `veteran`, which was not an allowed synonym replacement for `old`.
- Oracle contrast: parses `main.log`, builds substitutions only from `synonyms.txt`, repeatedly compiles and substitutes one allowed synonym until no overfull boxes remain.
- Wattle behavior: achieved no overfull hbox warnings, but violated the allowed-edit contract.
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
- Raw lesson: ML tasks need validation that matches the verifier input format and threshold with margin; internal split success can be misleading.

### `video-processing`

- Status: failed.
- Verifier: landing frame was 230; expected inclusive range 231 to 234.
- Oracle contrast: uses frame-level movement/background subtraction and task-specific thresholds to locate jump start/end.
- Wattle behavior: got very close but failed an off-by-one/tolerance-sensitive boundary.
- Raw lesson: video/temporal tasks need exact boundary calibration and verifier-range checks before final answer.

## Running Or Incomplete At Snapshot

### `model-extraction-relu-logits`

- Status: running at the snapshot.
- Current evidence: Wattle had inspected `forward.py` and found that the hidden layer shape is directly present in the importable implementation, but no completed `result.json` had been synced yet.
- Oracle contrast: uses query-only critical-point sweeps against `forward()` to recover rows of `A1` up to permutation and scale, then writes `/app/steal.py` and `/app/stolen_A1.npy`.
- Do not classify yet. It should be analyzed after a completed `result.json` is synced.

### `sam-cell-seg`

- Status: running at the snapshot.
- Current evidence: Wattle had begun a MobileSAM-based mask conversion task, but no completed verifier result was synced yet.
- Oracle contrast: installs the pinned MobileSAM implementation, uses the provided box masks as prompts, converts all masks to non-overlapping contiguous polylines, and writes an output CSV matching the input schema.
- Do not classify yet. It should be analyzed after a completed `result.json` is synced.
