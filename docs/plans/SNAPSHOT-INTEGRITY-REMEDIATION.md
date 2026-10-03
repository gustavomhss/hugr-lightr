# Snapshot integrity remediation — execution specification v2.2

**Repository:** `gusmhs/hugr-lightr`

> Migration note: active campaign tracking is [issue #5](https://github.com/gusmhs/hugr-lightr/issues/5);
> recovered package IDs are in [the issue map](../migration/issue-map.jsonl).
> Original numbered references, approvals and evidence below retain historical
> repository context; they are not new execution authorization or current links.

**Date:** 2026-09-16  
**Integration branch / PR:** `fix/snapshot-integrity` / [#146](https://github.com/gmhelmold/hugr-lightr/pull/146)  
**Revision scope:** planning documents and execution packets only. This revision does not implement or validate Rust fixes.  
**Status:** PUBLISHED FOR PLANNING; implementation NOT STARTED. Campaign #152; SI-00 #153. Read `DISPATCH.md` before acting.
**Revision base:** v2.1 at `fda407e11de7516a812c321ed29bd1798fc48edc`. This targeted planning amendment incorporates integrated-review A01–A05; A06 native tracking remains separately verified or blocked in DISPATCH.md. No runtime qualification is implied.
**Second-review response:** V2-A01–V2-A06 have selected planning dispositions below. Model/document checks are not Rust qualification.  
**Supersedes:** v2.1 at `fda407e11de7516a812c321ed29bd1798fc48edc`; preserves earlier technical decisions except the explicit refinements below and rejects v1's unconditional parallel READY states.  
**Code baseline:** `e4a53417f6fe7da8c4f44908af9525536443d0fa`; pre-fix base `5c5ca00008ed0d22673be79a7b585517527418af`; planning head inspected for this revision `fda407e11de7516a812c321ed29bd1798fc48edc`.

## 0. Use, authority and meaning of completion

This document specifies the observable behavior first and derives work packages and experiments from it. The protocol below is a selected design for implementation and review, not a menu delegated to competing agents and not an already proven implementation. A demonstrably incompatible primitive blocks the affected package and requires an explicit amendment; it is not permission to invent a different commit protocol locally.

The owner authorized **the integrated-review refinements and tracking synchronization, within the plan-only scope already established**. This authorizes editing the specification and preparing/synchronizing its tracking metadata, not launching workers, editing Rust/CI, creating new execution services, merging, enabling auto-merge, releasing, changing billing/permissions or modifying sibling repositories. Future implementation needs a separate execution instruction and the gates below. Read `CLAUDE.md`, `CONTRIBUTING.md` and applicable accepted ADRs; this plan does not silently change their acceptance status.

Campaign [#152](https://github.com/gmhelmold/hugr-lightr/issues/152) tracks the six work packages. Keep the original five implementation issues, #147–#151; coordinator/bootstrap SI-00 has its own issue [#153](https://github.com/gmhelmold/hugr-lightr/issues/153). PR #146 remains the separate integration deliverable. Native hierarchy/dependency/Project state is recorded in `DISPATCH.md`, not inferred from these links. Each work package contains five distinct, mandatory axioms:

| Axiom | Question it answers |
|---|---|
| **Success Criteria** | Which observable outcome must the package produce? |
| **Quality Standards** | Under which implementation and evidence constraints is that outcome acceptable? |
| **Completeness Criteria** | Which exact surfaces, scenarios and deliverables must be covered? |
| **DoD** | What evidence, review and integration transitions allow the package to close? |
| **Invariants** | Which properties must remain true throughout all its transitions? |

These sections are cumulative, not interchangeable headings. A green test count is neither completeness nor DoD. The protocol can be specified while execution prerequisites remain unmet. Do not label either implementation or qualification complete from a documentation commit.

### Scope and limits

In scope: owned staging, CAS publication and reuse, capture freshness, ref/history publication and recovery, authoritative GC roots, active materialization, affected metadata consumers, causal tests, native-platform evidence and performance acceptance.

Out of scope: runtime/memoization redesign, new engines, Docker feature expansion, seccomp, CoreLink changes, full CAS scrub/repair, arbitrary hostile modifications to private store files, network filesystems and unsupported mounts, atomic snapshots of an actively mutating entire directory, universal power-loss certification. A corruption encounter must fail safely even though repairing all historical corruption is out of scope.

LMF1 and current RefRecord encodings remain unchanged and readable. The selected protocol uses **object-readiness receipts and one bounded pending-operation descriptor per ref**, as in v2.0. V2.1 extends that SAME descriptor to a fixed named-image tuple and a decision phase, and specifies tagged version envelopes in the EXISTING history plane so past metadata is not lost. Legacy log records remain decodable but are not retroactively certified. These are explicit protocol/history-schema changes requiring an accepted ADR before implementation; they are not claimed format-neutral or compatible with concurrent old writers. No third request ledger, general-purpose transaction database, recovery daemon or emergency-space reservation is added. SI-00 freezes concrete bounds, compatibility and the internal result types; user-facing recovery/support changes require its compatibility review.

## 1. Evidence baseline — facts, not current qualification

[Original audit](https://github.com/gmhelmold/hugr-lightr/pull/146#pullrequestreview-5227371146). Original [CI run 35139596421](https://github.com/gmhelmold/hugr-lightr/actions/runs/35139596421) tested checkout merge `609bbf6ed919a3af56f2345444f55b45d8c0ebb9`, not merely a branch name. The inspected Linux x86_64/macOS arm64 logs showed the 12 added tests passing. Formatting failed. macOS arm64 [job 104940488434](https://github.com/gmhelmold/hugr-lightr/actions/runs/35139596421/job/104940488434) failed in `acceptance_r1::g1::a11_gc` during the FIRST snapshot, before GC, with ENOENT. Windows builds/clippy were not native execution of the new tests. Rust is pinned to `1.96.0` in the baseline.

The plan adversarial review identified R01–R14. Its auxiliary filesystem experiment and two transition models were not Rust or crash-durability tests. The historical ENOENT cause remains unproved. No new passing CI, available executor, platform capability or performance number is asserted by this revision. The second review is `Lightr-Plan-V2-Adversarial-Review.md`; V2-A01–A06 below are planning responses, not closed runtime defects. The later integrated review is `Lightr-Revisao-Integrada-v2.1.md`; its A01–A06 IDs are distinct from V2-A01–A06. Its read of CI run `35158370442` / checkout `7c456be923d100f124ec7239612a4d7929284ec6` found configured Linux/macOS acceptance passing, formatting failing, and zero artifacts for the CI benchmark aggregator. The step named Verify no regressions only echoed a manual-review message; this is not performance evidence. The separate benchmark-evidence workflow was not audited. These are historical observations, not a new run or an explanation of the original ENOENT.

## 2. Selected contracts

### C01 — Success, failure and platform assurance

Separate **content integrity**, **fresh capture**, **visibility**, and **durability**. They must not share an ambiguous boolean.

Internally, publication reports its operation ID, phase, original error/cause and one of these outcomes. Names are semantic requirements; SI-00 maps them to the existing error/CLI surface without discarding OS error information.

| Outcome | Meaning and permitted caller behavior |
|---|---|
| `NotPublished` | No commit decision for this operation was installed or attempted with an uncertain result. Physical tuple components may have been staged in their named locations under PREPARED, but guarded readers cannot use them; recovery restores the exact previous tuple. Orphan CAS objects are allowed. Retry only after pending resolution. |
| `CommitUncertain` | Installing/confirming COMMIT_DECIDED may have succeeded, but confirmation failed or the result is unavailable. Recover the durable journal phase; do not infer the decision from current alone, roll back a known decision, or automatically replay snapshot/undo/untag. |
| `CommittedMaintenanceFailure` | Payload, named-tuple/history barriers and COMMIT_DECIDED confirmation succeeded; journal cleanup/retirement or ancillary maintenance failed. Retain the logical change and finish recovery, never replay or roll it back. |
| `Published` | Required payload, ref/history and journal-resolution steps completed at the platform's declared assurance level. Only this is ordinary successful completion. |
| `RecoveryRequired` | Pending/malformed/ambiguous state prevents safe progress. No destructive GC or guessed history. Preserve the original cause. |
| `RecoveryBlockedResources` | The required recovery is known but cannot complete because space, quota, inodes or another explicitly reported resource is unavailable. Preserve the underlying PREPARED/COMMIT_DECIDED state; follow C13. This is not permission to discard metadata. |

**Request attribution is a separate result axis (V2-A05).** Inspection reports the current coherent tuple and journal state independently from `RequestIdentified` or `AttributionUnknown`. A matching retained pending operation ID can identify that operation; after journal cleanup there is no guaranteed persistent request-identity record. Equal roots, full records, timestamps or history entries prove state, not which request caused it. A lost response with no matching journal returns AttributionUnknown even when state is healthy. It does not create RecoveryRequired or imply corruption. No automatic replay of a non-idempotent request; a new explicit user instruction is a new operation, not a claim of exactly-once delivery. Test pending present/absent and a subsequent concurrent writer. No extra request ledger is introduced.

The assurance baseline is process-crash recoverability plus checked file synchronization. Linux/macOS additionally require directory-entry barriers on validated local filesystems. Windows must check writable-handle file flushing, but **must not claim directory-entry power-loss durability merely from `FlushFileBuffers`**. A stronger requested guarantee on an unsupported profile fails explicitly; no silent downgrade. SI-00 records each supported profile and how its guarantee is exposed without inventing a new CLI flag as an implementation shortcut.

A process kill/reopen test establishes process recovery only. File/directory ordering plus fault-injection tests establish implementation obligations under documented OS assumptions, not proof against lying devices or arbitrary filesystem corruption. A failed flush is never dismissed by simply retrying that syscall and calling the old bytes durable. [P1–P4]

### C02 — One GC lease and an explicit lock order

C12 path preflight precedes operation-owned filesystem writes. Top-level operations acquire one store-scoped GC lease: SHARED for capture/publication and materialization; EXCLUSIVE for collection or explicit metadata recovery. Low-level calls borrow that lease rather than reopening/reacquiring the global lock. Parallel child work must finish before its parent lease is released.

Order: **store-global lease → optional shared-cache resource lock → ref lock(s), sorted by ref key → digest lock(s), sorted when multiple are needed**. The cache section is a leaf: release its resource lock before acquiring any ref/digest lock; never acquire a cache lock while holding either. A digest lock must never be held while acquiring a ref lock. Payload preparation may precede ref locking only when all its digest locks are released first. No lock upgrades, recursive acquisition, or call from an exclusive-lease path into a wrapper that takes a shared lease. Standalone cache operations that have no Store acquire only the cache resource lock and never call into a Store while holding it.

Use store-canonical identity, stable lock files and both thread/process-correct exclusion. Do not delete lock files on unlock: replacing a lock inode can split the lock domain. Prove same-process behavior rather than assuming an OS lock also serializes threads. Keyed in-process mutexes may complement kernel locks. Independent refs must progress concurrently. Lock waits need cancellation/cleanup; correctness tests use bounded watchdogs, not timing assumptions about fairness.

**Resource domains (integrated-review A01):** a Store lease excludes only that Store's participants; it is not proof of quiescence in a shared index. Preserve the existing shared index location, but assign that cache root one stable native-identity-keyed resource lock. All cache loads/publications, initialization/probes that mutate it, and scratch reaping take that resource lock exclusively for their short filesystem section. The lock covers cache staging allocation through install/cleanup, not the source walk, payload hashing or a user command. Build candidate index records outside the cache lock; cache remains non-authoritative and last-writer replacement is not a freshness proof. Store-bound callers acquire the Store lease first; standalone status/index callers use the same cache lock without inventing a Store. Both thread and process exclusion are required. No blanket Store-global mutex is introduced.

| Managed resource | Participants / exclusion | Permitted scratch cleanup |
|---|---|---|
| Store-private CAS/ref/receipt/pending metadata and their staging | Same canonical Store identity; its SH/EX lease and existing key locks | That Store's EX lease, limited to its registered owned staging |
| Shared index cache and its staging | Every Store and standalone cache caller sharing the resolved cache-root identity; the cache resource lock | The cache resource lock held EX, regardless of which Store initiated cleanup |
| Owned internal workspace staging | Its inventoried owner/resource guard retained by every helper | Only the matching resource domain; no sibling traversal |
| Unknown, overlapping authoritative roots or legacy scratch with unproved ownership | No inference from path spelling or a foreign Store lease | Reject/skip safely until an explicit ownership rule is accepted |

SI-00 records each namespace's resolved identity, participants, lock identity, allocation lifetime and cleanup boundary, including alias spellings. Same-root aliases must share a lock domain; distinct Stores sharing a cache must share its cache lock. Reaping with Store A's EX alone cannot touch shared-cache or Store B scratch. A cleanup pass acquires each needed resource guard in the order above, never multiple Store leases or multiple cache locks at once; pending inspection requiring ref locks is completed/released before entering the cache section. Stable resource-lock files are never scratch and are not replaced at unlock. Unknown alias equivalence or overlapping authoritative Store roots is UnsupportedTopology, not a guessed domain. This registry is reviewed configuration/ownership information, not a new persistent transaction ledger. [P6–P7]

`PreparedObject` is an internal proof tied to the live lease and digest, produced only after C03 completes. It cannot be forged from `exists`, a stat-index entry or an arbitrary path. The per-lease dedup map contains only completed preparations; failures wake all waiters with an error, not a permanently pending promise. Borrowing/scope prevents use after lease release. Persistent readiness receipts are checked under C03; they are not a substitute for a live lease protecting an object from collection.

### C03 — Owned staging and safe reuse after failed finalization

Allocate a private temporary directory atomically on the destination filesystem, only inside the collector-known managed staging namespaces defined by C13. Place a **nonexistent** payload path inside it for CoW operations. Use exclusive creation and bounded collision retries; PID/time/randomness may choose names but are not the ownership guarantee. Reserve at most 32 candidate names before returning a contextual allocation error. Cleanup owns only that directory and never a published object or another writer's allocation. RAII handles normal exits, not abrupt process death; C13 supplies a separate quiescent scratch-reclamation contract.

A valid object-readiness receipt is stored separately under a sharded private `objects-ready` namespace. Its bounded, versioned contents bind digest, length, protocol version, assurance profile and checksum. It is written **only after** the corresponding payload and required namespace barriers complete. Receipt and object reads reject symlinks, malformed records and mismatched identity. Receipts are not GC roots. They do not certify a copied/moved store on an unqualified destination filesystem; an offline move/import needs target-side qualification. All participating writers must use this protocol; mixed legacy writers are unsupported.

The selected publication algorithm is:

1. Capture bytes from the selected live source or, for a digest-only operation, use a verified streaming read of the existing CAS object. Reject wrong type, missing bytes, digest mismatch and read errors. Do not follow a substituted store symlink.
2. Stage privately. New live-source capture may use a supported CoW clone; fallback is a complete checked copy. On failed CoW, remove only the operation's own incomplete payload before fallback. Hash the final owned staged file, derive its length there and compare any externally supplied expected identity. Retain checked handles/ownership through publication.
3. Under the digest lock, first consult an existing valid receipt and validate its object. A completed proof in the same lease can be reused directly; a cross-operation receipt requires identity/content verification before creating this lease's proof. **A receipt-confirmed object is immutable: later normal writers do not replace it**, even with identical bytes. This prevents another writer's failed replacement from invalidating an earlier successful publisher's proof.
4. If no valid receipt exists, path presence is not readiness. An existing unconfirmed or legacy object must validate against the expected digest, then be requalified by a full ordinary byte rewrite into a fresh owned file, not a hardlink, reflink of the potentially failed object, or fsync-only retry. Re-hash the final replacement. A malformed receipt or corrupt object is explicit RecoveryRequired/Integrity, not silent repair. Requalification touches only the required object, not a whole-store scrub.
5. Apply final payload permissions/attributes before its last data/metadata synchronization, retaining rights needed to flush on Windows. Never mutate live-source attributes. Install verified bytes atomically under the digest lock; synchronize the destination directory and each newly created ancestor needing a barrier. No fallback unlinks a destination before replacement. Only unconfirmed objects may be replaced by this path.
6. After payload confirmation, atomically write the readiness receipt and perform its required synchronization. Only then report ordinary successful preparation and create `PreparedObject`. If receipt finalization fails, report the phase; do not roll back/delete the now-confirmed payload. A following caller either validates a fully readable receipt (whose publication was ordered after payload confirmation) and reconstructs the receipt in a fresh private file with checked barriers, or requalifies without relying on a missing receipt. It never upgrades an unconfirmed payload by existence alone.

Receipt synchronization is not confused with payload synchronization: a valid visible receipt can only have been constructed after successful payload barriers. Loss of that receipt after a crash loses an optimization/proof, not the data guarantee; requalification is then required. Bad/missing payload despite a receipt fails integrity checks. A subsequent caller may use validated immutable bytes only under the declared assurance profile, never claim that retrying a failed data fsync repaired them.

The safe staging and phase-reporting rules apply to `ingest_file`, `put_bytes` and shared atomic metadata writes. Metadata writes report whether replacement happened before error; `Err` does not always mean no effect. Standalone low-level calls do not protect a later ref write after their lease ends; transaction-aware callers borrow one lease across the entire operation. Preserve public wrappers where possible.

**Post-payload-rename failure:** the object may remain but no receipt/readiness proof is issued. This operation cannot publish a ref. A following operation must perform fresh requalification or fail. A mere read-back is insufficient. Known storage I/O faults stop the affected operation; no automatic loops claim the device is healthy. Successful fresh requalification is a new transaction, not repair certification for unrelated storage.

**GC and receipts:** under the EXCLUSIVE lease, invalidate/remove and confirm the receipt before deleting an unreachable payload. If that prerequisite fails, do not delete the payload. A crash between those steps leaves an unconfirmed orphan, not a stale readiness certificate. Receipt absence never authorizes deleting a reachable object. The object/receipt pair is not claimed to be an atomic two-file transaction; the ordered states deliberately remain safe.

Within a capture, identical digests share a completed preparation and waiters receive the same success/failure, not N racing publications. Cross-operation reuse retains content verification and lease protection. The cost of receipts, verification and legacy adoption is measured under C10; no unreviewed persistent fast path is added to meet a benchmark.

### C04 — Freshness: snapshot derives identity from captured bytes, not stat guesses

All snapshot-producing entry points use a verified capture path. For a source stable for the duration of capture, the result must represent its current selected contents even when size, inode and mtime equal an earlier scan. The stat index may accelerate enumeration/planning/status heuristics; it may not supply a snapshot's final digest without reading/capturing this invocation's bytes.

Preferred dataflow: `capture selected file → owned stage → hash/size of stage → PreparedObject → manifest entry`. Streaming avoids loading whole files into memory. The internal capture/requalification/materialization pipeline must use a verified streaming reader rather than a whole-payload `get_bytes()` allocation; public byte-vector getters need not change their existing API. The manifest is built from these actual results; do not attach fresh metadata to an old cached digest. Preserve an expected-digest comparison where an API explicitly supplies a previously captured manifest. No implementation may bypass C03 through `Store::exists`.

Record file identity/type and metadata around capture. An observed identity/type change, vanished selected entry or inconsistent capture is `CaptureChanged`/a typed error, not omission. Default is one attempt and an explicit retryable error, not an unbounded rescan. Captured bytes must remain independent of subsequent source mutations. Undetectable concurrent rewrites and a globally atomic directory view are outside the guarantee; this does not excuse stale capture of an already stable source.

Traversal, metadata, read-link and hashing failures propagate for selected entries. Existing explicit ignore rules remain exclusions, not errors. Never turn a failed read-link into an empty target. Selected unsupported special files are rejected with a path/type error unless explicitly excluded by ignore policy. Permission experiments must prove the tested identity actually lacked access.

Build candidate index updates separately and publish them only after a successful scan. An unreadable/corrupt cache can be discarded and recomputed; a failed cache save is classified as cache maintenance, not proof that a ref failed after commit. Keep cache writes before ref commit where they remain required by an existing API. A later retry must work without manual cache deletion. Concurrent cache writers cannot share/truncate a staging file.

### C05 — Coherent named versions, history provenance and bounded recovery

**Publication unit (V2-A01):** for each name, `NamedVersion = (current RefRecord or absent, imgmeta pointer or absent, imgmanifest pointer or absent)`. The two pointers identify already verified immutable CAS data. `refs-names` is only a rebuildable lookup index. Readers of the image/config/export and writers of any of these THREE authoritative components participate in the same ref lock and pending check. A tree-only consumer may explicitly read only the tree from a classified legacy current, but cannot advertise validated OCI metadata. This is a fixed three-component transaction, not a generic multi-key engine. SI-00 must verify that the two known OCI pointers cover every version-owned named metadata family used by the affected consumers. An additional discovered family blocks the schema/caller gate until it is explicitly added with its own bounded field and oracle; it cannot be silently excluded from the coherence claim.

All producer dependencies are prepared BEFORE mutating named pointers: import/pull derives its tree from the verified layers and binds the matching verified config/manifest; tag reads one coherent source tuple under sorted source/destination ref locks; a metadata-only change is still a named-version change. The manifest/config descriptor relationship and the producer's tree association must validate before publication. Standalone pointer APIs must either enter this full transaction or return an explicit transaction-required/unsupported result; they cannot leave unjournaled named writes. A plain filesystem snapshot binds both OCI pointers to absent rather than inheriting stale image metadata. Build may bind a config without claiming a retained original OCI manifest. No-op compares the WHOLE intended tree/metadata tuple (not only the root); identical snapshots add no timestamp-only version. A metadata change with the same tree is not a no-op. Each top-level image/run-config/export operation resolves the complete tuple ONCE under its ref lock and then uses those captured immutable digests under its lease; sequential name-based getter calls are not a substitute. Unrelated standalone API calls do not promise a shared snapshot across intervening commits. Test a consumer paused between root resolution and config access against a concurrent writer.

**Existing history plane:** new numeric slots contain a bounded tagged `HistoryVersion` envelope: exact RefRecord bytes, the two optional OCI pointers and explicit provenance/kind. This keeps config/manifest associated with past versions after pending is deleted. A new decoder accepts both legacy raw records and tagged envelopes without ambiguous magic detection, unchecked lengths or silent coercion; SI-00 fixes a disjoint tag/encoding and limits before implementation. The new form does not repurpose reserved LMF1 fields or change the current RefRecord. Envelopes need no retained request ID. GC marks tree AND associated metadata/dependencies from every retained envelope. `undo` restores the chosen verified tuple, derives the new parent under the same ref transaction, and appends a new transition. `bisect` applies the provenance boundary and C07 materialization scope. History/export readers must never pair an old root with today's name-indexed config.

**One pending descriptor per ref:** bounded, checksummed and versioned; contains operation ID/kind, validated ref name/key, phase `PREPARED` or `COMMIT_DECIDED`, exact before/after values (including absence) for all three tuple components, reserved history slot plus exact expected envelope/hash, and any precise history-retirement identity. Any staged path is cleanup-only: no recovery outcome depends on a volatile staging file. Fixed component names are derived from validated keys, not arbitrary user-provided paths. Tuple/envelope fields and payload barriers are frozen with the schema in SI-00. Before/after CAS dependencies remain protected by the lease; unresolved descriptors prevent ordinary destructive GC.

Every normal current/image/history read or write acquires its ref lock under a SHARED global lease and checks pending first. A pending record blocks the affected read with RecoveryRequired, including sidecar-only getters. It may not expose a hybrid tuple or prepared history. Explicit recovery takes the EXCLUSIVE global lease, then ref/digest locks, using borrowed-lease APIs. Recovery checks that each observed component equals its recorded before or after value (or another explicitly recorded idempotent retirement intermediate); an unrelated value, malformed record or unrelated slot is RecoveryRequired with no guessed overwrite. A permitted old/new MIX is expected during a prepared transaction, not proof of outside corruption.

**Normal named update:**

1. Prepare verified dependencies, validate the complete intended tuple, release digest locks before acquiring sorted ref locks, and read current/derive parent under those locks. Resolve pending and legacy-boundary preconditions before deciding a no-op. Select `max(numeric slots)+1`, with checked overflow and collision-safe allocation; never file count. Reserve expected envelope bytes in the descriptor.
2. Install and confirm PREPARED before ANY tuple component or user-visible history namespace changes. Failure to confirm this descriptor permits no such change; a visible PREPARED is resolved first on retry.
3. Write/confirm the prepared history envelope. Install/confirm the two proposed named pointers (including checked removals), then current, through phase-aware helpers. Hold the ref lock throughout. These physical writes are NOT yet a logical commit. Nothing exposed through the supported readers can interpret this transient tuple as a completed generation.
4. Only after all payload, tuple and history barriers succeed, replace the SAME descriptor with COMMIT_DECIDED and confirm it. **Installing the valid COMMIT_DECIDED record is the logical decision/linearization point; successful confirmation is the acknowledgment barrier.** A failure in this replacement is CommitUncertain. This explicitly replaces v2.0's current-only decision point, so metadata-only updates and equal current bytes do not require invented timestamps/nonces in RefRecord.
5. Complete decision-dependent retirement if any, remove pending and confirm its directory before ordinary Published. A cleanup failure after confirmed decision is CommittedMaintenanceFailure. Optional names-index maintenance cannot roll back the tuple; any error remains a maintenance result.

**Recovery decision is journal-phase based, NOT a guess from current:**

| Valid observed journal | Idempotent recovery action |
|---|---|
| PREPARED | Validate observed components/owned slot against the descriptor. Restore exact BEFORE tuple through checked writes/removals, remove only the matching prepared envelope (already absent is valid), then clear/confirm pending. A new current that happened to be physically installed before the decision is restored too. Normal readers were blocked, and no commit decision was acknowledged. |
| COMMIT_DECIDED | Never abort. Requalify required AFTER dependencies using C03 if needed; finish/confirm exact AFTER tuple and matching envelope/retirement; clear/confirm pending. Report RecoveredCommitted for that journal's operation. |
| Missing journal | A guarded coherent state needs no journal recovery. A lost reply may have AttributionUnknown. Absence of a request ID never justifies rollback/replay. |
| Malformed phase, unrelated component/slot or unavailable required data | Stop with RecoveryRequired/Integrity. Resource exhaustion is RecoveryBlockedResources under C13, not silent success or forced rollback. |

The phase must remain sufficient if recovery itself is killed after any step. PREPARED rollback never rolls forward, and COMMIT_DECIDED recovery never rolls back. Interrupted journal replacement yields a valid old/new phase or an explicit metadata error, not guessed chronology. There is no supported point at which a reader can observe partial named metadata while pending is present. OS/power-loss assurances remain bounded by C01; synthetic failures do not prove hardware durability.

**Untag/recreation:** untag's AFTER tuple is all-absent. Under PREPARED, removing individual named components does not permit history retirement; abort can restore the before tuple. After COMMIT_DECIDED, finish removing the tuple and retire the exact prior-lifetime history/name-index namespace, then clear pending. Completed untag ends retention for that history except other roots and active readers. A recreated name cannot reuse unretired history or old OCI pointers. Any legacy orphan retirement is a separately recorded, fixed-kind maintenance transition under the same protocol, finished before the name is recreated; it cannot infer that an unrelated directory is disposable. A copied tag uses fresh destination record/parent semantics but the same source tree/config/manifest association.

**Legacy policy (V2-A03):** all raw pre-protocol history records are `LegacyUnverified`. Decode success, current==last-log, matching parents/timestamps or a matching internal chain do not certify historical publication. Preserve decodable legacy roots conservatively while the live name retains them; unreadable reachability still blocks sweep. A current tree may be read/verified independently. Legacy OCI pointers are `LegacyTupleUnverified` unless their association is established by explicit validation/adoption; content-valid individual blobs alone do not prove a coherent generation.

History inspection may show raw records with the explicit LegacyUnverified label. Default undo/bisect cannot select or cross that segment: return LegacyHistoryUnverified with a reconciliation path, not guessed history. To start verified work on such a name, explicit adoption establishes a NEW `ADOPTED_BASELINE` envelope for the currently verified tree and an explicitly validated/operator-selected metadata association, or explicit metadata absence. Record the provenance as adoption NOW, not evidence of what happened earlier. This special maintenance transition may append a baseline even when before==after; ordinary no-op rules do not suppress it. Adoption is journaled, non-lossy and does not delete or relabel the old segment. Future protocol transitions form a verified suffix; navigation is allowed inside that suffix including its adopted baseline. Reconciling older versions is an explicit operator decision and cannot manufacture proof of historic requests. SI-00 fixes the user-facing inspection/adoption contract before enabling migration. Mixed old/new writers and unqualified downgrade are unsupported.

### C06 — Strict root discovery and non-destructive uncertainty

GC takes the EXCLUSIVE Store lease and completes a full mark phase before deleting anything. FIRST enumerate the complete pending-operation namespace independently of current refs, names or history. Any valid unresolved operation blocks destructive CAS sweep, including a create with no current, PREPARED untag after physical current removal, and COMMIT_DECIDED untag awaiting retirement. Unreadable/malformed pending, a failed shard iteration or an unknown descriptor layout also blocks sweep. A pending namespace genuinely absent in a legacy/new empty store is not a read failure; absence must be established directly. Do not auto-recover before evaluating this precondition or limit pending checks to names discovered in refs. This is a strict pre-scan of the existing journal plane, not a new root ledger (integrated-review A04).

Only after that pre-scan succeeds, enumerate physical authoritative `refs` shards, decode each record, and verify the ref key/name relationship. ENOENT meaning an absent ref is different from an inaccessible shard or a decode error. Never use an empty `list_refs()` result as proof that all roots are absent.

For each live name, mark the coherent current tuple independently of retained committed/legacy history. Traverse the OCI pointers in each tagged history envelope as well as its tree; current name-indexed sidecars cannot substitute for historical bindings. Also preserve every existing root family: Action Cache records and retained OCI metadata/blobs, plus any additional family found by the SI-00 caller/root inventory. Each family needs a strict collector-facing enumeration path: display APIs may remain fail-soft, but their swallowed errors cannot feed destructive GC. Unknown pointer-bearing record formats, incomplete enumeration, pending ref operations, or unreadable required metadata abort the sweep. Do not silently remove an existing root family to simplify this campaign.

A missing referenced object is an integrity error, not an invitation to delete its remaining siblings. An absent optional root-family directory is allowed only when its absence is actually observed, not inferred from a failed read. Removed names do not regain roots merely because old log files exist. Sweep reports must distinguish candidates, objects actually removed, and failed removals. C13 scratch reaping is a separate restricted operation: it neither traverses/sweeps uncertain CAS roots nor overrides this all-roots mark prerequisite.

### C07 — Active readers and exact materialization

A hydrate operation acquires a SHARED lease before resolving its ref. Under the ref lock it obtains a stable committed tuple/envelope or fails on pending state; it never loads image pointers later through an unguarded name lookup. It releases the ref lock but retains the global lease through the last required object read/materialization. Concurrent untag may succeed; GC must wait until this materialization finishes. The output then consists of independent bytes, not borrowed mutable CAS storage.

Do not hold a store lease while running an arbitrary user command. `bisect` pins each materialization step, not the externally executing predicate; removal between steps may produce an explicit unavailable-history error. This limited guarantee must be documented. `undo` chooses an allowed-provenance target tuple and current parent under the same ref transaction and publishes a new transition, rather than copying stale parent metadata or pairing old tree data with the current image config. Lost-reply attribution follows C01, not automatic command replay.

Tree equality means entry kinds and relative component names, exact regular-file bytes/length, exact stored symlink target text, and explicitly supported metadata. Use an independent lstat/readlink/byte comparator, not the production manifest codec or path-normalizer as the sole oracle. Do not follow symlinks when comparing or writing descendants.

| Surface | Preservation or rejection rule |
|---|---|
| Names | Exact valid UTF-8 components; no lossy conversion or Unicode normalization. Relative manifest paths only; reject traversal, duplicate paths and file/link ancestor conflicts. Check encoding length limits. |
| Unix backslash | Preserve as a literal filename character; never rewrite it to a separator. |
| Destination aliases | Preflight case/Unicode/reserved-name collisions against the actual target filesystem using an owned reservation area; reject unrepresentable trees without overwriting user data. Do not assume all macOS/Windows volumes have the same case behavior. |
| Regular files | Exact bytes and stored Unix permission bits where supported. Windows preserves the supported read-only attribute, not fictional POSIX ownership/modes. |
| Symlinks | Preserve target text and representable link semantics under the class table below. Distinguish UnsupportedRepresentation from UnsupportedCapability. No silent copy, target-text rewrite or dangling-link omission. |
| Directories | Preserve representable directory paths, including empty directories. Existing format does not promise directory ownership, ACLs, xattrs or arbitrary directory modes. |
| Other metadata | Timestamps, ownership, ACLs, xattrs, hardlink identity and special files are outside exact-tree equality unless separately contracted. No hidden success claim for their preservation. |

**Windows link representability (V2-A04):** LMF1 stores only link path/target text, not a native file-versus-directory tag. No reserved-field reuse or new link-format extension is authorized in this revision. The chosen supported subset below is derived from the WHOLE captured manifest, never from a later live target lookup. [P5]

| Source/destination class | Required behavior |
|---|---|
| POSIX capture/materialization on a capable POSIX profile | Preserve valid UTF-8 target text, including dangling links. Cross-platform representability is not implied. Reject text/paths the existing codec cannot represent. |
| Windows source link to a directly represented in-tree regular file or directory | Allow only if the link target can be resolved entirely from the captured tree by exact relative components, without passing through another link, case/Unicode alias, external/absolute/device path or cycle, and the source's native link-kind flag agrees with the derived kind. Stage/validate the WHOLE tree before acknowledging capture. |
| Windows source directory/file link with absent, external, chained or otherwise ambiguous target | UnsupportedRepresentation before snapshot publication, even with administrator/link privilege. Do not guess type from a missing target or silently drop the entry. |
| LMF1 materialization on Windows with unambiguous direct in-tree target | Derive file/directory kind from the manifest's regular/explicit-or-implied directory entry, materialize targets before links, and use the corresponding native API mode. Creation still requires independently verified capability; failure is UnsupportedCapability or the original I/O error. |
| LMF1 materialization on Windows with ambiguous/unrepresented target | UnsupportedRepresentation at preflight. Permission alone cannot recover missing type information. |

The selected portable Windows target subset uses relative UTF-8 components separated by forward slashes, with dot/dot-dot resolved lexically without leaving the captured root or traversing another link. Stored target text is not rewritten. Backslash-containing, absolute, drive-relative and device targets are outside this subset and receive UnsupportedRepresentation. SI-00 pins tests of accepted forward-slash and rejected backslash forms, not a choice of alternative semantics. Broader native syntax requires an explicit support amendment, not a local normalization shortcut. The codec remains readable for old manifests; unsupported materialization is an explicit behavior boundary, not success with lost information. A test unable to create its native source fixture records NOT_EXERCISED, not a representability pass. Capture tests include file/dir links and BOTH kinds of dangling native links under actual capable Windows execution.

Hydrate must validate C12 topology and names/types before user-output writes. On later failure it reports failure and the partial-output/owned-cleanup policy, never success with omissions. It must not delete a pre-existing user directory during cleanup. Atomic all-or-nothing destination replacement is not promised by this campaign.

### C08 — Observable failure boundaries

The table concerns this operation's effects, not global rollback over another writer. Tuple means all three C05 components. Physical current replacement alone no longer decides the transaction.

| Failure boundary | CAS / tuple / history state | Next legal action |
|---|---|---|
| Topology/representation preflight rejects | No prohibited source/destination or named-state mutation | Correct paths/support; do not silently ignore managed directories or recode links |
| Capture/staging/verification fails | No new named tuple/history; owned scratch and prepared orphan CAS objects may exist | Owned cleanup; C13 reaping handles abrupt death |
| Payload installed; required barrier fails | Visible object without readiness proof; no new tuple/history | Fresh qualified rewrite or fail; existence-only reuse prohibited |
| Dependencies ready; PREPARED not confirmed | Before tuple/history; possible pending file, no permitted component change | Resolve visible PREPARED; retry only after cause corrected |
| PREPARED; any subset of pointers/current/prepared envelope installed | Supported readers refuse pending state; physical components are recorded before/after values | Restore BEFORE tuple and remove matching prepared envelope; no ghost version/hybrid read |
| COMMIT_DECIDED installation/confirmation fails | CommitUncertain; observable valid journal may be PREPARED or COMMIT_DECIDED | Follow observed valid phase; never decide from root equality |
| COMMIT_DECIDED confirmed; cleanup/retirement fails | CommittedMaintenanceFailure; AFTER tuple is retained | Finish recovery/retirement without replay |
| Process dies before reply; matching pending remains | That operation can be identified; journal governs recovery | Resolve its phase; report attributable recovered outcome |
| Process dies before reply; no matching pending remains | Store may be healthy; current does not prove request identity | Return state facts plus AttributionUnknown; no automated undo/snapshot/untag replay |
| Recovery hits ENOSPC/EDQUOT/inode or storage-resource failure | Decision/evidence and retained objects stay protected; no false completion | RecoveryBlockedResources plus C13 scratch/operator runbook; full GC stays blocked while uncertain |
| Root discovery incomplete or tuple/provenance metadata unreadable | No destructive CAS sweep | Restore access/reconcile; retry strict discovery |
| Reader active; untag commits | In-flight coherent materialization protected by lease; new readers may see absence | Complete active reader, then collection |
| Legacy interior is unverified although current matches last raw log | Current tree remains separately readable; old history not certified | Labeled inspection or explicit adoption/reconciliation; no default navigation across unverified segment |

### C12 — Disjoint public namespaces and handle-grounded preflight (V2-A06)

The public path policy is **disjoint, not implicitly ignored**. A filesystem capture source may neither equal, contain nor lie inside any protected store/index/staging namespace. A public materialization destination may neither equal, contain nor lie inside those namespaces. For operations that actually accept BOTH a live source and a live destination, those two paths must also be disjoint. A stored snapshot is not a remembered live source path; do not invent such a path to apply this rule. Existing empty-destination/pre-existing-user-directory rules still apply.

SI-00 inventories the exact configured protected roots, including the CAS/ref/history/pending/receipt/lock families, index cache and each managed scratch area. Run-workspaces are not automatically forbidden just because they are siblings under LIGHTR_HOME; an internal build/hydrate adapter uses a verified owned-workspace capability and remains disjoint from authoritative metadata. Public input strings or an internal-looking prefix cannot mint that capability. Raw CAS/readiness adoption uses its internal digest API, not a public recursive capture of the store.

Resolve public path components with native, anchored filesystem semantics BEFORE deciding identity/ancestry. Never lexically collapse `component/..` before resolving that component: it may be a symlink or mount boundary. Preserve native errors, required directory/trailing-slash semantics and the requested object; validation and use must address the same opened object/anchored parent, not separately reinterpret strings. For example, with `workspace/alias -> store/branch`, `workspace/alias/../payload` resolves through the link to `store/payload`, not lexical `workspace/payload`. Use a native component walker/handle primitive that preserves this meaning, or explicitly reject an unsupported topology before writes. Dot/dot-dot resolution within C07's already restricted in-manifest Windows link subset is a different operation; it does not authorize lexical cleanup of arbitrary public paths. [P6]

Validate a not-yet-created destination against its natively resolved nearest existing ancestor before creation, then revalidate the created/opened directory. Retain handles or equivalent anchored traversal across the operation so an ordinary alias race cannot redirect writes. If a mount/alias relationship cannot be established on a supported profile, reject as UnsupportedTopology; do not claim all possible mount aliases were verified. Network/unsupported filesystems remain outside scope.

CLI orchestration performs configured-root preflight before mutable Store initialization/probing when it owns that initialization. An API given an already-open Store validates before its own capture/preparation/output writes; it cannot undo earlier actions by its caller. Internal owned staging is the only bounded exception to public path disjointness and cannot be selected as user input. No silent ignore insertion, source mutation or deletion of pre-existing user directories to make topology valid.

Required witnesses: equal paths; store/index inside source; source inside store; destination inside/above managed roots; source/destination overlap in a paired operation; symlink/alias spelling; `alias/../payload` with distinct native/lexical targets; dot segments without links as a control; a missing destination under a resolved alias ancestor; trailing slash on file versus directory; harmless sibling-prefix names; allowed isolated internal workspace. Use independently opened object identity/content, not the normalizer under test. Assert rejection before prohibited mutations using independent before/after observations.

### C13 — Resource-bounded recovery and safe interrupted scratch (V2-A02)

**Selected guarantee:** safety is unconditional within the fault model; recovery progress is conditional on resources. This plan does NOT promise recovery with zero free space/quota/inodes and does not add an emergency reserve. When the recorded action cannot allocate/confirm what it needs, return RecoveryBlockedResources with original error, journal phase/operation ID where available, resource domain and a safe next step. Do not repeatedly loop, erase pending or free potentially reachable CAS/history to obtain space.

**Scratch reaping is not full GC.** Every private allocation is made under one of SI-00's finite collector-known staging roots on the destination filesystem (for example a managed parent's dedicated `.lightr-staging/alloc-*` directory), while holding its actual resource-domain guard from C02. New-protocol namespaces contain only owned scratch, never user payloads or committed metadata. A synchronous reaper acquires the matching exclusion before removing abandoned allocations: Store EX for Store-private staging; the shared cache's EX resource lock for cache staging, even when invoked with Store A's EX already held. Store A's lease says nothing about Store B or a standalone cache caller. All helpers/child processes retain the applicable guard for their full allocation lifetime. Quiescence follows only within that proven domain, never from a foreign lock. The reaper rejects symlink traversal and unknown layout/ownership, checks pending descriptors, and skips anything referenced or not provably scratch. C05 recovery data is inline or in ready CAS, never solely in scratch. A malformed/legacy descriptor that prevents this proof blocks that cleanup subset, not permission to guess. Timestamps, age and PID reuse are not ownership proofs. Stable lock files, current/log/sidecars/receipts and CAS payloads are NEVER scratch.

The reaper must not allocate new staging as a prerequisite for starting; deletion can nevertheless fail on a full/broken filesystem and that error remains explicit. Reap only recognized leaves/allocations through anchored paths, confirm removals where supported, and make interruption idempotent. Partial/unknown old `.tmp` layouts are not deleted merely because their names look temporary; SI-00 must either establish a migration-specific ownership rule or leave them for explicit operator handling. No background daemon or relaxed full-GC mode is introduced.

**Operator runbook, required as an executable support surface before qualification:**

1. Stop retrying the failed mutator. Inspect the recorded operation read-only; quiesce participating writers and retain the journal/retained data. If inspection itself lacks memory/descriptor capacity, stop safely and report that prerequisite rather than a fabricated state.
2. Run only the resource-domain-guarded scratch reaper. Report attempted/removed/skipped/failed items separately, including inability to acquire the actual shared-cache domain; never substitute a Store lease for it. Full CAS GC still requires complete roots and an independent empty-pending pre-scan.
3. If resources remain insufficient, free unrelated data OUTSIDE protected namespaces or increase the relevant filesystem/quota/inode allowance. Do not ask the user to delete pending/current/history/CAS by hand. Never choose an arbitrary user file for deletion.
4. Report a conservative resource estimate before retry: sum of lengths of dependencies needing ordinary requalification (not merely the largest blob), bounded metadata/history/pending temporary writes and the measured profile's directory/inode overhead. Report bytes and inodes/quota separately. This is an estimate, not a guarantee against concurrent external consumption; inability to compute it remains a blocker. SI-00 supplies concrete schema bounds and reproducible per-profile headroom tests, not a made-up universal MiB constant.
5. With resources restored, run idempotent recovery under EX, verify the complete BEFORE or AFTER tuple/history as dictated by phase, clear/confirm pending, hydrate/check the expected data, then permit ordinary GC. Recurring resource loss returns the same explicit blocker without changing the decision.

Evidence must exercise synthetic failure at each allocating boundary AND actual constrained-resource execution on a disposable supported filesystem/quota setup where available. At least one real no-space recovery/retry scenario is mandatory; quota/inode capability gaps are distinct unexercised profile rows and cannot be renamed passes. No host disk is filled. Test PREPARED rollback, COMMIT_DECIDED completion, zero reclaimable scratch, pre-journal scratch from killed capture, a live helper holding its lease, recovery/reaper interruption and resources lost again during retry. Prove the safe operator intervention resumes work; lack of resources before intervention is not itself an integrity failure.

## 3. Global invariants

| ID | Required property |
|---|---|
| I01 | Stable-source capture is fresh; stat equality never substitutes for this invocation's bytes. |
| I02 | Published digest/length refer to owned verified bytes; cleanup cannot affect another allocation. |
| I03 | No readiness receipt/proof before required payload barriers; confirmed objects are immutable to normal writers; existence is not readiness. |
| I04 | Each Store operation holds one correctly scoped Store lease; shared resources use their own exclusion domain; no nested global acquisition or reversed resource/ref/digest order. |
| I05 | PREPARED work is not committed history; rollback restores the complete before tuple and never overwrites another decided operation. |
| I06 | Current, OCI metadata, parent and version history form one guarded named generation; the explicit journal phase, not current alone, decides recovery. |
| I07 | Independent pending discovery and authoritative root discovery both complete before sweeping; no current-less pending or enumeration error becomes empty success. |
| I08 | Acknowledged current/history data remain retained while the name is live, except an explicit retention/untag action; active materialization stays protected. |
| I09 | Names, links and topology are preserve-or-reject; public path resolution preserves native symlink/parent semantics and validation/use identity; no lossy or redirected success. |
| I10 | Evidence identifies the code, binaries, tests and platform actually exercised. |
| I11 | Resource/performance acceptance is decided from preregistered measurements; no optimization weakens integrity to pass. |
| I12 | Scope, ownership and authorization remain explicit; no source execution or merge is implied by this plan. |
| I13 | Resource exhaustion never authorizes discarding pending evidence or incomplete-root CAS sweeping; recovery progress conditions and safe operator intervention are explicit. |
| I14 | Legacy provenance and request attribution are honest information boundaries: state equality never manufactures historical commit or request-identity proof. |

## 4. Work graph and integration ownership

```text
SI-00: contract ratification + caller inventory + platform/test capability
   ├── SI-01: shared CAS/lease/result foundation ── G-FOUNDATION ──┐
   └── SI-02: pure capture/oracle work against frozen seam ──────┤
                                                              v
            SI-03: ref/history/GC + callers/readers → G-ACTIVATION
                                                              v
                     SI-04: integrated adversarial proof suite
                                                              v
                  SI-05: independent qualification + perf gate
                                                              v
                              owner review (no auto-merge)
```

SI-02 may implement its pure traversal/oracle portion in parallel with SI-01 only after SI-00 accepts the seam. Its production integration and DoD depend on G-FOUNDATION. SI-03 does not start implementation against changing CAS/lock semantics. Ref locking and the snapshot caller are integrated in SI-03, not deferred to a later test-only package. SI-04 may review/design experiments from SI-00 onward, but cannot qualify nonexistent integrated behavior. Test infrastructure is delivered in SI-00, not postponed to SI-05.

### Activation boundary — foundation is not product enablement (integrated-review A03)

The selected transition is **additive, inert foundation followed by one coordinated source-level activation**. SI-01 adds new lease/preparation/receipt primitives; SI-02 adds capture/path primitives. Before activation they are exercised only through controlled tests on isolated disposable fixtures. Existing public dispatch/wrappers remain on the old path; no new readiness/history/pending data is emitted into a real store, no real-store adoption occurs, and no environment flag or partial adapter silently enables the protocol. Existing legacy defects are not declared fixed by keeping that path unchanged. Intermediate integration binaries are not qualified for real data. CI still exercises required old-path regression coverage plus the isolated new primitives.

**G-FOUNDATION** certifies the accepted seam and isolated primitive evidence only. Its acceptance explicitly records `production_protocol_enabled=false`; it neither satisfies whole-product invariants nor permits migration. SI-02 may close its primitive package after real prepare/capture tests, while every publishing caller remains an explicit SI-03 integration obligation.

**G-ACTIVATION**, owned by SI-03 and approved by the coordinator after contract review, requires one exact integrated source identity containing every participating writer, public wrapper/caller, reader, root-family adapter, pending pre-scan, scratch-domain rule and recovery path. SI-03 flips public routing only in the final coordinated integration slice, with public CLI/API tests proving borrowed single leases, zero recursive global acquisition, strict current-less-pending handling, full tuple coherence and refusal of recognized incompatible/partial protocol states before mutation. Activation is first exercised against disposable stores. It is not SI-05 qualification or permission to migrate the owner's data. Whole-product invariants become acceptance obligations at this gate; their real evidence is then challenged by SI-04/05.

Keep one SI-03 acceptance responsibility, with ordered reviewable slices: codecs/decision; producers and callers; readers/history; GC/recovery/reaping; final activation. Slices may use separate PRs targeting the integration branch but cannot change the shared protocol independently or close the WP early. Review required changeover callsites in SI-00 and recheck them at G-ACTIVATION. A partial/new-format encounter returns an explicit incompatibility/recovery error, never legacy fallback. No new activation ledger or store-format flag is introduced by this planning amendment; the accepted schema/compatibility ADR must define detectable states and offline upgrade/downgrade handling. Old processes cannot be assumed to obey a new refusal rule: mixed writers remain unsupported and operationally excluded before later authorized adoption. Failure to demonstrate safe coordinated activation blocks SI-03 rather than relaxing invariants.

At most two implementation workers run in the initial wave; read-only review can be a third role. One writable worktree/branch per worker. Every worker targets a draft PR at `fix/snapshot-integrity`, never main. Coordinator integrates one reviewed change at a time after checking the exact expected head; no force-push. Rebase/reconcile moved inputs and rerun affected tests. Package artifacts stay isolated; issue prose cannot override this specification.

### Work package SI-00 — freeze seams and make evidence executable

**Tracking:** [#153](https://github.com/gmhelmold/hugr-lightr/issues/153), campaign #152. **Owner:** coordinator. **Entry:** later execution authorization. **Dependencies:** none.  
**Ownership:** accepted design/compatibility records, caller/root inventory, dedicated test-support and minimal CI wiring, evidence validator and baseline fixtures. No remediation source edits except explicitly reviewed internal seam declarations if needed before fan-out; these cannot change behavior.

#### Success Criteria

- SC00.1: C01–C08 and C12/C13 map to named functions/types and callers, with no conflict between helper and transaction outcomes.
- SC00.2: each required native platform executes a smoke witness and returns readable logs/results before its dependent implementation claims readiness.
- SC00.3: incident diagnostics, test-oracle recipes and performance methodology are available to implementers from the start. The accepted foundation seam includes bounded receipt and pending-descriptor formats, not just Rust signatures.
- SC00.4: ratify the full named-version tuple, decision phase/history schema, legacy adoption/navigation boundary, link-class table, AttributionUnknown axis and path/resource preconditions before affected implementation. Also freeze namespace/lock/cleanup domains, native public-path semantics, G-FOUNDATION versus G-ACTIVATION and the independent pending pre-scan.

#### Quality Standards

- QS00.1: read applicable ADRs; record acceptance of the readiness-receipt, fixed-tuple pending/decision protocol and tagged history envelopes, including intentional semantic changes before implementation. No silent format/dependency promotion.
- QS00.2: add narrowly scoped CI/support only; preserve unrelated workflows, security boundaries, tests and failure visibility. Historical skips are inventoried, not copied into causal suites.
- QS00.3: capabilities require receipts, not runner labels or API permissions. Pin the baseline toolchain; resource costs are disclosed. Do not infer shared-cache quiescence from a Store lock or treat a green echo-only comparison as evidence.
- QS00.4: extend existing protocol planes only; no new request ledger, emergency reserve or hidden link encoding. Any simplification must still satisfy the six V2-A oracles.

#### Completeness Criteria

- CC00.1: enumerate all callers of `atomic_write`, `ingest_file`, `put_bytes`, `ref_put`, `ref_get`, `ref_log`, `ref_remove`, `list_refs`, GC root loaders and `materialize_file` at the frozen SHA; classify mutation/read behavior and test ownership.
- CC00.2: include snapshot, build snapshotting, tag/import metadata, history/undo/bisect, hydrate, AC and image sidecars. Out-of-scope consumer behavior still receives regression coverage if a shared helper affects it.
- CC00.3: deliver `platforms`, `seams`, `caller-map`, `expected-tests`, incident hypothesis table and fixture hashes as compact evidence records. All relevant CI/bootstrap paths have an owner.
- CC00.4: establish privilege-aware Windows symlink and Unix permission tests, actual CoW/fallback reporting, artifact collection, exact-SHA checkout verification and a nonzero-test smoke run. Create the performance baseline and budget-registration step in C10.
- CC00.5: include OCI sidecar-only readers and all mutators, profile-specific resource headroom/runbook, native link-type inspection, alias identity APIs, legacy raw/envelope fixtures and the matching semantic reference for EACH performance fixture (especially F6). Add a resource-domain map covering standalone index callers, an activation/caller map, two-Store shared-cache fixtures, symlink/parent fixtures and pending-without-current fixtures; inventory the observed CI aggregator defect.

#### DoD

- DOD00.1: contract/compatibility review is recorded; mandatory profiles have capability receipts or clearly blocked downstream work. An unavailable platform is not a pass.
- DOD00.2: inventory and test identifiers are reviewed; evidence-validator negative fixtures reject wrong SHA, empty suite and missing artifacts.
- DOD00.3: coordinator publishes one exact foundation input SHA and accepts the seam definitions. Only then can SI-01 and SI-02's isolated portion become READY. Nothing is marked implemented by SI-00 alone.
- DOD00.4: V2-A01–A06 each have an accepted policy, owner and E17–E22 recipe; descriptor/envelope bounds, migration entry and safe support commands are specified. Approval is planning approval, not a claimed executed prerequisite. Integrated-review A01–A05 must map to these gates and existing E08/E11/E15/E18/E22; native tracking A06 remains separate from runtime acceptance.

#### Invariants

- INV00.1: I10/I12; no credentials, sibling changes, invented runners or fictitious agents.
- INV00.2: authoring the plan is distinct from executing this bootstrap; current capability entries remain NOT VERIFIED until measured.
- INV00.3: shared semantics do not change while independent workers consume them; an amendment invalidates affected readiness/evidence. G-FOUNDATION is explicitly inert; no issue/PR status authorizes protocol activation or real-store migration.
- INV00.4: I13/I14; unavailable evidence remains unavailable, and neither legacy history nor absent request identity is certified by inference.

### Work package SI-01 — CAS, staging, lease and phase-result foundation

**Tracking:** [#147](https://github.com/gmhelmold/hugr-lightr/issues/147). **Owner:** storage foundation implementer. **Entry:** SI-00 accepted.  
**Ownership:** `lightr-store/src/store/cas/**`, required CoW helper changes, global lease/digest-lock primitives, Store wrappers and minimal phase-result definitions. Those shared files are exclusively owned here until G-FOUNDATION. Per-ref transaction logic belongs to SI-03. Mechanical formatting is a separate commit.

#### Success Criteria

- SC01.1: a collision or failing copy cannot touch another operation's staging, and the public entry point cannot bypass staged verification.
- SC01.2: a failed post-install barrier cannot become a later successful existence-only reuse; C03 requalification or an explicit failure occurs.
- SC01.3: checked native flushing, single-lease composition and concurrent same-digest publication satisfy C01–C03 without changing payload encoding; confirmed objects cannot be replaced by later writers. These are additive primitive guarantees at G-FOUNDATION, not enabled public routing; actual shared-resource guards follow C02.
- SC01.4: every scratch allocation is in a known managed namespace; resource failures preserve evidence and wake waiters without retry loops. Preparation never publishes OCI named pointers.

#### Quality Standards

- QS01.1: RAII ownership, atomic reservation, bounded retries, streaming buffers and typed contextual errors; no full-file memory buffer, unsafe destination unlink, hardlink to live input or fsync-only recovery.
- QS01.2: no process-global failure hooks. Use scoped test seams sharing the production path and retain original error kind/phase. New unsafe or platform-specific code receives line-level review. No source switch or configuration shortcut activates the new protocol before G-ACTIVATION; cache guards obey the resource-domain order.
- QS01.3: native clone and copy-fallback outcomes are reported separately; Windows source read-only attributes and flush-handle rights are exercised, not inferred from a build.
- QS01.4: scratch is not a recovery data source; allocation/cleanup are lease-scoped and compatible with C13 EX reaping. Do not reserve emergency storage or invent a guaranteed zero-space path.

#### Completeness Criteria

- CC01.1: implement all C03 call sites, not only `finish_ingest`; update the caller inventory and preserve metadata-writer behavior required by SI-03.
- CC01.2: E01–E04 and E09: forced allocation collision, threads/processes, failed fallback, source/staged mutation, wrong digest/length, zero/large/read-only files, valid/missing/malformed readiness receipts, existing valid/corrupt destinations, immutable confirmed-object reuse, post-rename failure/retry, flush failure and nested-lease negative controls.
- CC01.3: mechanical rustfmt fixes and diagnostics-only incident probes are separately attributable. Preserve original fixture; use C09 to distinguish the ENOENT hypotheses.
- CC01.4: test lease-local dedup failure wake-up, cancellation, object count semantics and progress across distinct digests. Orphan cleanup must not require a new daemon.
- CC01.5: E18 resource failures and pre-journal killed-worker scratch; bounded streaming requalification headroom, clone/copy partial failures, known/unknown staging layouts and live-child lease ownership. C12 guards all public source paths. Exercise distinct Stores sharing an index, aliases of one Store/cache root and standalone cache writers; EX on a foreign Store must never authorize cache scratch collection.

#### DoD

- DOD01.1: targeted store tests/formatter/clippy and required native witnesses pass at the exact worker SHA; mutants have their specified dispositions.
- DOD01.2: independent or explicitly labeled self-review checks phase propagation and lock lifetime, including shared helper consumers. No surviving causal mutant is ignored.
- DOD01.3: coordinator integrates the reviewed foundation, verifies its seam matches SI-00, and records G-FOUNDATION. Incident status may remain unresolved, but must remain an explicit final gate; no false causal closure. The receipt must state production_protocol_enabled=false and list every caller still awaiting SI-03 conversion; no real store is adopted.
- DOD01.4: give SI-03 the actual scratch inventory and phase-aware primitives; show data/journal preservation for allocation failures and that candidate cleanup does not reclaim a live helper allocation. Final reaper/runbook qualification remains SI-03/04/05, not falsely completed here.

#### Invariants

- INV01.1: I02/I03/I04; a proof is issued only for fully prepared bytes and cannot outlive its lease. Resource proofs never outlive or cross their actual lock domain, and primitive availability is not product activation.
- INV01.2: errors after visibility are not rewritten as no-effect failures; already committed user refs are untouched by CAS cleanup.
- INV01.3: platform failures propagate; no performance shortcut reintroduces stat/existence trust across operations.
- INV01.4: I13; insufficient space never turns an unconfirmed object into ready data or erases a pending operation.

### Work package SI-02 — fresh, fail-closed capture and faithful path semantics

**Tracking:** [#148](https://github.com/gmhelmold/hugr-lightr/issues/148). **Owner:** capture implementer. **Entry:** SI-00 seam accepted. **Production integration dependency:** G-FOUNDATION.  
**Ownership:** scan/capture implementation and index cache internals in `lightr-index`, pure path validation/oracle fixtures and capture tests. No CAS, global locks, refs, GC or snapshot orchestrator changes. SI-03 wires the verified path into every publisher.

#### Success Criteria

- SC02.1: warmed-index AAAA→BBBB with restored stat fields captures BBBB on a stable source; all snapshot identities come from this invocation's captured bytes.
- SC02.2: selected traversal/read/metadata/link failures cannot yield a successful incomplete capture; correcting the cause permits a fresh retry.
- SC02.3: supported names/types are preserved exactly; invalid/unrepresentable paths are rejected rather than silently normalized.
- SC02.4: C12 rejects overlapping protected paths; C07 differentiates link representation from native privilege. No source tree is silently changed to fit support. Public alias/../path follows native resolution or explicit refusal; it cannot be validated or executed as its lexical substitute.

#### Quality Standards

- QS02.1: stage-derived length/digest, bounded memory and one-attempt changed-source policy; no blanket retries or special-casing fixtures.
- QS02.2: preserve explicit ignore rules. Permission tests run under an identity proven unable to read the target; root bypass is not success evidence.
- QS02.3: the oracle uses independent filesystem observations and bytes, not the implementation's index/codec as its only truth source.
- QS02.4: infer any supported Windows link kind only from the full captured manifest and verified source kind, not a later target lookup; no reinterpretation of LMF1 reserved fields or prefix-only path checks. Do not collapse component/.. across an unresolved link; preserve trailing-slash/errors and use the object or anchored parent that preflight actually validated.

#### Completeness Criteria

- CC02.1: E05/E06/E12 and capture parts of E03: restored mtime/inode/size, stale/corrupt cache, failed cache save/retry, vanished entry, unreadable subtree, failed read-link, valid/dangling links, empty directories and source changes.
- CC02.2: Unix literal backslashes, UTF-8 rejection, alias collisions, path traversal/ancestor conflicts, codec length limits and intentionally ignored files are explicit tests.
- CC02.3: produce a verified capture result against the real SI-01 seam plus compatibility tests for existing scan/status consumers. Pure seam doubles are not final production-path evidence.
- CC02.4: E20/E22 include native file/dir links, both dangling kinds, direct in-tree versus external/chained targets, enabled/disabled capability, source/store/index overlap and alias spellings; failed preparation leaves no named state. Add two targets with different bytes for native-versus-lexical resolution, dot-only controls, missing descendants and trailing-slash cases; shared-index publication uses C02 resource exclusion.

#### DoD

- DOD02.1: pure tests may be reviewed early; package closure waits for G-FOUNDATION integration and real prepare/capture tests on supported profiles. These witnesses use controlled fixtures and do not enable production routing; SI-03 owns G-ACTIVATION.
- DOD02.2: removing freshness/error propagation must fail the designated negative witnesses or receive a justified equivalent-mutant classification after redesign.
- DOD02.3: coordinator records the integrated capture SHA and hands the actual function/call-site list to SI-03. No source-data identity decision remains implicit.
- DOD02.4: support/rejection and topology oracles pass against real capture APIs; a fixture not created is NOT_EXERCISED. Record producer-level validation needed by SI-03 before any snapshot commit.

#### Invariants

- INV02.1: I01/I02/I09; the index never certifies a snapshot's bytes, and a failed read never becomes an ignore rule.
- INV02.2: no silent change of filename, link kind or target text; unsupported metadata is not advertised as preserved.
- INV02.3: failed capture does not mutate ref/history; unrelated concurrent commits are not rolled back. Index scratch is protected by the shared-cache resource lock, not a guessed Store identity; public caller activation is not performed here.
- INV02.4: I09/I13; unsupported representation and resource exhaustion cannot become partial successful capture.

### Work package SI-03 — one coherent ref/history/GC and reader integration

**Tracking:** [#149](https://github.com/gmhelmold/hugr-lightr/issues/149). **Owner:** transaction integration implementer. **Entry:** SI-01 foundation and SI-02 production seam integrated; pending-protocol ADR accepted.  
**Ownership:** refs/per-ref locks/pending descriptor/history envelope codec, named OCI sidecar readers/writers and import/pull/tag/export/build adapters, strict root loaders/readiness-receipt invalidation, GC/recovery/scratch-reaper entry points, `snapshot.rs` and CLI topology adapters, hydrate and timeaxis/history consumers. Core/shared signature changes require coordinator review. SI-01 global/CAS primitives are consumed, not independently redefined. This deliberately replaces the v1 split between SI-03 and the later SI-04 publisher edits.

#### Success Criteria

- SC03.1: current/parent/history implement C05/C08, including interrupted updates and untag/recreation. A failed prepared B never turns `[A,P]` into a false history `[B,A,P]`.
- SC03.2: authoritative refs cannot disappear from GC because a name index was omitted or unreadable; no destructive sweep follows incomplete root discovery. Pending discovery is independent of current/names/history, including interrupted create and both untag phases with no current.
- SC03.3: the real snapshot entry point uses verified capture/preparation; active hydrate survives concurrent untag+GC under C07.
- SC03.4: readers obtain a coherent tree/config/manifest generation or an explicit error after every interrupted publication, including metadata-only changes. Recovery either progresses under C13 resources or reports the actionable blocker without deleting retained evidence.

#### Quality Standards

- QS03.1: one bounded per-ref journal, explicit outcomes and fixed lock order; no generic WAL/database or silent on-disk migration. All consumers obey pending-state checks.
- QS03.2: preserve original error and operation identity; legacy ambiguity is explicit. Do not invent chronology, reinterpret attempted versions as committed, or resurrect untagged roots.
- QS03.3: keep unrelated ref progress and existing AC/image-root retention. Names/log display conveniences never determine destructive authority. Every reaper uses its actual namespace guard; G-ACTIVATION is a coordinated source transition, not mixed new primitives with old wrappers/GC.
- QS03.4: PREPARED/COMMIT_DECIDED is the single decision rule for the fixed tuple; all sidecar APIs participate. LegacyUnverified and AttributionUnknown remain distinct from corruption, and no extra request ledger is added.

#### Completeness Criteria

- CC03.1: E07–E11/E13/E14 plus all C08 boundaries, exercised through both public APIs and CLI where applicable.
- CC03.2: include `ref_put`, removal, same-name recreation, snapshot parent read, tag/import root publication, history/undo/bisect, hydrate, names-index discovery, all existing GC root-family adapters and legacy fixture decoding.
- CC03.3: verify log gaps/overflow/exclusive allocation, pending checksum/path validation, PREPARED/COMMIT_DECIDED recovery and unrelated-component rejection, interrupted retirement, missing names, malformed current/log/sidecars and incomplete shard enumeration.
- CC03.4: implement targeted recovery entry/diagnostics and demonstrate that recovery itself is idempotent after interruption; no manual deletion of pending files is presented as recovery.
- CC03.5: E17–E22 cover failures before/after each OCI pointer/current/decision write, same-root metadata updates, tag over existing destination, historical tuple undo, full/zero-scratch recovery, quota/inodes, interrupted recovery/reaping, interior legacy ambiguity, lost replies and caller topology. Run GC immediately after restart BEFORE manual recovery with current-less pending; exercise shared-index reaping across two Stores and verify all public lease/caller routes at activation.

#### DoD

- DOD03.1: no partial integration declares ref serialization complete while its snapshot caller still reads parent outside the protocol. All affected consumer tests accompany the same reviewed integration unit.
- DOD03.2: each C08 row has an observed correct result/recovery; old/new trees are compared against independent fixture bytes, not merely return codes.
- DOD03.3: coordinator reviews compatibility, recovery and caller/root completeness, integrates the unit and publishes the candidate SHA for SI-04. Known unresolved integrity failures block this transition. Record G-ACTIVATION and its exact source identity only after the final coordinated slice passes public-path tests; earlier slice integration cannot close SI-03 or authorize real-data use.
- DOD03.4: compare the COMPLETE named tuple/history on rollback and rollforward; demonstrate safe operator-assisted no-space recovery, old-name metadata retirement, verified-suffix navigation and blocked legacy selections. Lost request attribution cannot trigger replay. These adapters ship with the protocol, not deferred as documentation.

#### Invariants

- INV03.1: I03–I09; prepared logs are never visible committed versions and current remains an independent GC root. Strict pending pre-scan precedes all CAS deletion even when refs is empty; Store EX never substitutes for exclusion of shared-cache users.
- INV03.2: no ref-level error handling undoes another writer's commit; uncertain visibility is never reported as guaranteed rollback.
- INV03.3: a reader's lease covers its last required read, not an arbitrary external command; untag defines an explicit retention boundary.
- INV03.4: I06/I13/I14; no hybrid named state, no unsafe resource escape, no retroactive history/request certification.

### Work package SI-04 — causal proof of the integrated behavior

**Tracking:** [#150](https://github.com/gmhelmold/hugr-lightr/issues/150). **Owner:** adversarial test implementer/reviewer. **Entry:** integrated SI-03 candidate; test design can start earlier read-only.  
**Ownership:** dedicated adversarial tests, isolated mutant patches, evidence and small test-support adapters. No unilateral production fixes, shared workflow changes or weakening of earlier tests; findings return to their owning package.

#### Success Criteria

- SC04.1: each invariant has a witness capable of distinguishing the candidate from a relevant faulty implementation.
- SC04.2: tests prove contenders reached the intended boundary without requiring a correct implementation to enter a mutually excluded region.
- SC04.3: process-death/retry/reader scenarios match C08 and exact output-tree checks, not just helper behavior. Include GC-before-recovery current-less pending, cross-Store resource contention and the post-G-ACTIVATION public entry point.
- SC04.4: E17–E22 distinguish complete-tuple consistency from root-only checks, real resource progress from return codes, and classified unknown information from fabricated success.

#### Quality Standards

- QS04.1: scoped seams, barriers/channels and nonblocking acquisition probes; sleeps are not scheduling proof. Watchdogs bound failures but do not by themselves establish mutant causality. Prove which lock namespace is contested; an EX probe on an unrelated Store is not evidence of shared-cache exclusion.
- QS04.2: classify every mutant as KILLED_CAUSALLY, SURVIVED, EQUIVALENT_WITH_PROOF, NOT_EXERCISED or INVALID_TEST. Do not weaken redundant protections to force a kill.
- QS04.3: no global environment mutation hooks, leaked children, dirty mutant delivery tree or production-only bypasses hidden behind mocks.
- QS04.4: constrained-resource tests use disposable capacity, not the host disk; models stay labeled models. Link tests establish native kind/capability premises and attribution controls do not inject a fake persistent request ID.

#### Completeness Criteria

- CC04.1: execute E01–E22, using real implementations/public paths where specified, and cover every C08 failure row. Any equivalent control gets an alternate causal witness for the invariant.
- CC04.2: separately remove the relevant verification path, freshness rule, lease interval, history filtering/recovery and strict-root behavior; verify intended assertions, then restore and rerun the candidate.
- CC04.3: exercise multiple writers and processes, independent refs, failure cancellation, exact old/new bytes, bounded retries and no source mutation after successful preservation affecting CAS.
- CC04.4: interrupt both transaction phases and recovery; cover tuple component mixes, same-current metadata-only transitions, legacy equal-tip ambiguity, no-scratch operator intervention, Windows ambiguous links, pending absent/present lost replies and filesystem-alias topology. E08/E11 add no-current journal phases; E18/E22 add multi-Store shared cache and native symlink/parent identity; no new experiment family is needed.

#### DoD

- DOD04.1: the reviewer inspects each oracle and actual synchronization trace. Empty/filtered-away suites, compilation failures and unrelated test failures do not qualify.
- DOD04.2: no unexplained surviving causal mutant; all execution receipts identify source/binary hashes and restored-tree checks. Production defects reopen SI-01/02/03 and invalidate dependent evidence.
- DOD04.3: coordinator integrates only test/support/evidence changes, revalidates the full integrated candidate and hands SI-05 a frozen code/test/workflow identity. Confirm the candidate includes G-ACTIVATION; primitive-only receipts do not establish public behavior.
- DOD04.4: reviewers trace all six V2-A obligations through the corresponding axiom/test/result, including correct refusal paths. Additive envelopes must pass legacy decode/provenance checks and composite history/GC oracles before handoff.

#### Invariants

- INV04.1: I05/I10/I12; test controls cannot become delivered production behavior or harm real user data.
- INV04.2: a correct lock design must terminate under the test harness; causality is established by checkpoints, not guessed timing. Test oracles compare the natively opened target and the actual resource domain, not the implementation normalizer or a foreign lock.
- INV04.3: independent review is not claimed when the implementation author reviewed itself.
- INV04.4: I13/I14; no unsafe deletion or reconstructed-but-unproved chronology in fixtures or delivered helpers.

### Work package SI-05 — native qualification and product acceptance

**Tracking:** [#151](https://github.com/gmhelmold/hugr-lightr/issues/151). **Owner:** reviewer distinct from implementation when available. **Entry:** SI-04 candidate frozen and C10 budget registered.  
**Ownership:** qualification runs, compact evidence records and comparison results. CI infrastructure already exists from SI-00. Missing wiring reopens SI-00; source defects return to their owners rather than being silently fixed during certification.

#### Success Criteria

- SC05.1: mandatory native profiles execute the expected causal/acceptance tests at the actual candidate identity; qualified claims match platform capability. The frozen identity must include G-ACTIVATION, not merely G-FOUNDATION.
- SC05.2: C09 incident disposition and C10 performance acceptance are explicit, supported and reviewed; no unexplained candidate snapshot failure is ignored.
- SC05.3: a fresh checkout can reproduce recovery/materialization and reject invalid evidence using the documented commands.
- SC05.4: qualification reproduces complete named-generation recovery and the C13 operator path; unsupported link classes, legacy boundaries and unknown request attribution have verified user-visible outcomes.

#### Quality Standards

- QS05.1: pinned toolchain, exact checkout and binary hashes; distinguish tested PR merge from branch head. Existing failing baselines remain visible.
- QS05.2: no blanket skips, `continue-on-error`, retrospective budget relaxation or benchmark claims from missing artifacts. Physical power-loss guarantees are not inferred from process kills. A performance verdict requires complete artifacts and an executed numeric comparison; an echo, skipped producer or zero-artifact aggregate cannot pass.
- QS05.3: review residual risk, performance and backward compatibility, not only build/check statuses. Self-review cannot be labeled independent.
- QS05.4: F6/composite-history budgets use a correct reference with SI-03 semantics, not a partial CAS foundation. Recovery headroom is per profile and not advertised as a universal free-space guarantee.

#### Completeness Criteria

- CC05.1: targeted store/index tests; real CLI acceptance; pinned formatting/clippy; impacted consumer regressions; E01–E22 dispositions; Linux x86_64/aarch64, macOS x86_64/arm64 and native Windows store/index execution with capability-specific rows.
- CC05.2: compare base, audited patch and final candidate fixtures; include checked failure/recovery, native CoW versus copy and the existing macOS failure reproducer. Execute full workspace checks on supported feature/target combinations established in SI-00.
- CC05.3: fill evidence schema, retention/expiry, independent review identity, budget verdict, incident disposition and all R01–R14 and V2-A01–A06 implementation-evidence links. Design closure is not implementation closure. Include integrated-review A01–A05 execution evidence; A06 tracking status is reported separately and never substituted for technical gates.
- CC05.4: require V2-A01–A06 disposition/evidence in addition to R01–R14; include real constrained-resource coverage, all supported/rejected Windows link-class rows, complete tuple import/tag/export/undo, legacy adoption, lost reply and disjoint-path CLI tests.

#### DoD

- DOD05.1: all mandatory rows have valid evidence, no unresolved integrity blocker or causal survivor remains, and the fresh-checkout reproduction passes. Verify independent journal discovery, shared-resource safety, native path identity and coordinated activation, plus actual budget comparison rather than its step label.
- DOD05.2: performance thresholds registered before final candidate measurement are met; otherwise BLOCKED_PERFORMANCE or an explicit owner-reviewed plan amendment followed by new measurements.
- DOD05.3: coordinator records QUALIFIED for that exact identity only. PR remains draft until the owner decides it is ready for review; main merge/release require separate owner action. No automatic merge.
- DOD05.4: no V2-A planning disposition is mistaken for code closure. Missing mandatory resource/tuple/provenance evidence blocks qualification; only the validated candidate and explicit profile limits may be accepted.

#### Invariants

- INV05.1: I01–I14; qualification cannot weaken any contract to create a green status.
- INV05.2: missing native capability/evidence is not cross-compilation success, and an expected Unsupported test is not an exercised feature.
- INV05.3: later code/test/workflow changes invalidate affected qualification; documentation-only provenance is handled explicitly under C11. An activation/caller change invalidates public-path evidence even if primitive tests remain unchanged.
- INV05.4: I13/I14; safety persists when progress is resource-blocked, and accurate refusal/unknown outcomes are not relabeled feature successes.

## 5. Experiments and causal oracles

Each E-row is a required experiment family. SI-00 resolves it to exact test names; SI-04 checks that they actually execute. A short implementation-specific subcase list is allowed, but no E-row disappears silently.

| ID | Setup/checkpoint and observable oracle | Negative control / owner |
|---|---|---|
| E01 | Force the same allocation candidate twice; first payload remains byte-identical, second retries/errors without unlinking it. Cover failed clone and partial fallback. | Nonexclusive reserve/unlink-other control; SI-01 |
| E02 | Synchronize threads AND subprocesses preparing identical digests; read all resulting bytes, prove one lease-local completion is shared and every waiter terminates on failure. | Shared-temp and premature-ready controls; SI-01 |
| E03 | Change supplied source/stage at the actual expected-digest verification boundary; mismatch fails before readiness/ref publication. For stage-first capture, prove the final digest denotes that owned stage, not an earlier stat observation. | Bypass production verification, not just its helper; SI-01/02 |
| E04 | Fail directory confirmation AFTER object install, end A, then run B in another process. B must perform fresh qualification or fail; it cannot return success on path existence. Also prove a later writer cannot replace an already receipt-confirmed object. Fail payload and receipt flush separately. | Exists-only and unchecked-flush controls; SI-01 |
| E05 | Warm index with AAAA; rewrite BBBB at same length/inode and restore mtime before capture. Decode via independent oracle and hydrate BBBB. | Stat-only digest reuse; SI-02 |
| E06 | Select unreadable/unhashable file/subtree, vanished entry and failed read-link. Public capture/snapshot fails; fix cause and recover previous then new tree. Verify permission premise under actual identity. | Swallowed-IO/empty-link controls; SI-02/03 |
| E07 | Begin with coherent tuple A/history [A,P]; fail B under PREPARED before OR after physically replacing current. Normal readers refuse; recovery restores the full A tuple/[A,P], and undo targets P. | Expose prepared history or use current-only recovery; SI-03 |
| E08 | Fail before/after COMMIT_DECIDED installation/confirmation and at every cleanup/retirement boundary. Resume from the valid journal phase; no double undo, ghost version or old metadata resurrection. Also restart interrupted create/PREPARED untag/COMMIT_DECIDED untag with no current; attempt GC before manual recovery and require zero required-blob deletion. | Ignore decision phase / treat all errors as rollback; SI-03 |
| E09 | Pause publication after readiness but before ref commit. Collector signals its attempt OUTSIDE the guarded region, performs a nonblocking EX probe and reports WouldBlock. Release writer, then collector completes; hydrate exact bytes. | Shorten every effective protection of interval; redundant guard removal may be equivalent; SI-01/03/04 |
| E10 | Force history allocation contention; B reports a failed nonblocking ref-lock probe rather than being required to enter A's region. After A releases, both complete with distinct history slots and parent order. | Remove serialization/allocation exclusion; SI-03 |
| E11 | Current A with legacy log B or a matching tip with unverified interior; missing/bad names index; failed authoritative shard/root-family iteration; unreadable current/log/AC/image metadata. No destructive sweep on uncertain reachability; retain decodable legacy roots without certifying chronology. Independently enumerate pending with refs/names empty; reject unreadable pending shards and all current-less phases. A refs-derived-only pending mutant must fail. | Names-only/skip-error/current-not-marked controls; SI-03 |
| E12 | Fixtures with links, empty dirs, literal backslashes, case/Unicode aliases and invalid paths. lstat/readlink/raw-byte comparator checks preservation or explicit preflight rejection. | Lossy normalize/follow-link comparator controls; SI-02/03 |
| E13 | Reader resolves A and pauses before final object read; untag commits; collector nonblocking probe is excluded until reader completes. Future new reader sees absence. | Drop reader lease; SI-03 |
| E14 | Existing tag/import/build/history/undo/bisect and root-family fixtures run through changed helpers; repeated snapshot/no-op and recreate-after-untag policy are explicit. | Consumer-bypass/missing-root fixtures; SI-03 |
| E15 | Give evidence validator a wrong checkout/binary, zero tests, skipped required test, absent artifact, dirty mutant or stale workflow. Each is rejected; valid receipt accepted. Include the observed zero-artifact/echo-only benchmark aggregate: missing required profile, duplicate/malformed/nonfinite metric or absent numeric comparison fails; baseline evidence validity and final budget acceptance remain distinct. | Permissive evidence gate; SI-00/05 |
| E16 | Bounded seeded stress complements deterministic schedules; record concurrency, operations, seed and output trees. Compare incident diagnostic/control variants under C09. | Original faulty fixture/control where applicable; SI-04/05 |
| E17 | Prepare image B while A is live; fail at every pointer/current/log/decision boundary. Guarded tree/config/export readers observe A, B or explicit pending error, never a hybrid. Include same-root metadata-only update, tag over B, historical tuple undo, untag/recreate and two same-name writers. | Publish named sidecars outside journal / root-only no-op / history without metadata; SI-03/04 |
| E18 | PREPARED and COMMIT_DECIDED recovery exhaust bytes/quota/inodes; full GC remains blocked. Exercise killed pre-journal scratch, live helper exclusion, no reclaimable scratch, safe external headroom intervention, interrupted reaping/recovery and retry. Two distinct Stores share the index; keep B or a standalone cache writer active, prove A reaper waits on the CACHE domain or safely skips it, then cleans only after exclusion. Store-private scratch remains scoped; alias identities share a domain. | Delete pending to gain space / incomplete-root sweep / age-only scratch deletion; SI-01/03/04/05 |
| E19 | Two legacy execution histories leave identical raw records (tip matches; one interior attempt was never committed). Both classify LegacyUnverified. Explicit adoption adds a present-day baseline without rewriting old history; undo/bisect only traverse the verified suffix. | Tip equality certifies all history / silently drops suspected entries; SI-03/04 |
| E20 | Actual native Windows file/dir links and both dangling kinds, direct captured targets versus ambiguous targets; test capable/incapable profiles. Prove class/capability refusal separately and exact supported link reconstruction from manifest, not live target guessing. | Erase type information then guess / copy fallback / mark uncreated fixture passed; SI-02/03/04/05 |
| E21 | Lose reply with matching PREPARED/COMMIT_DECIDED present, then with no pending, and after another writer updates state. Inspection separates recovered effect from AttributionUnknown; no automatic repeat/rollback is executed. | Root/record equality proves request ID / replay unknown undo; SI-03/04 |
| E22 | Capture with store/index inside source, source inside store, paired source/destination overlap, managed destination, aliases/missing descendants, and harmless sibling-prefix control. Assert rejection before prohibited writes and allow isolated internal owned-workspace adapters. Include native alias/../payload versus lexical substitute with distinct bytes, dot-only and trailing-slash controls, and missing descendants. Assert opened-object identity, not string normalization; repeat shared-cache and Store alias domains. | String-prefix-only checks / implicit ignore or caller-forged internal capability; SI-00/02/03/04 |

Every concurrent experiment has: fixture identity; checkpoint outside/inside the relevant critical section; proof of contender arrival; expected observations before release; explicit release; bounded join; owned cleanup. Never wait for a correct contender to enter a region the lock intentionally excludes. Nonblocking probes demonstrate exclusion; watchdog timeouts only report harness/system failure until a trace explains causality.

For each mutant record compilation result, actual executed test names, failing assertion/trace, and restored-candidate rerun. `SURVIVED` on a relevant behavioral mutation blocks closure. `EQUIVALENT_WITH_PROOF` requires reviewed control-flow/redundancy reasoning and an alternative witness, not relabeling a weak test. Crashes of the test harness, compile errors and unrelated failures are not killed mutants.

## 6. C09 — ENOENT incident investigation without causal overclaim

Use the existing `a11_gc` fixture unmodified: 200 identical 1 KiB files, nested directories, executable file, symlink, empty directory and its large file. Keep formatting-only, diagnostics-only and causal implementation commits separable. Diagnostics record operation/staging identity, syscall stage, paths, digest prefix, actual copy rung/fallback and original error; never payload contents.

| Hypothesis | Distinguishing observation / controlled intervention |
|---|---|
| H1 staging name collision | Two operations claim the same temp path; forced name collision reproduces ownership violation; exclusive reservation changes that exact behavior. |
| H2 destination-finalization race | Different staging paths, same destination; failure at install/attribute/barrier. Serialize finalization without changing source allocation to isolate it. |
| H3 source/path failure | Original source open/stat/read fails; staging/destination changes alone do not explain it. Reproduce source lifetime/path resolution independently. |
| H4 CoW fallback failure | Trace identifies failed native clone and fallback/partial destination handling; force copy-only versus actual clone with identical fixture. |

These hypotheses are not asserted equally likely or exhaustive. Add one only with a discriminating observation. Compare base, audited patch and candidate using the same diagnostics patch where behavior-preserving. Record when instrumentation alters timing.

Disposition is `CAUSE_CONFIRMED` only with a causal trace plus a reproducer/control that distinguishes the repair. Otherwise use `HISTORICAL_CAUSE_UNRESOLVED`, even when a real allocator bug is fixed. An unexplained candidate failure always blocks qualification. If the historical incident cannot be reproduced after a bounded investigation, only an explicit owner-reviewed risk disposition can replace causal closure; do not stall indefinitely or silently call repeated passes proof. The investigation budget is preregistered in SI-00 as run counts/platforms, not an invented completion-time promise.

## 7. C10 — Performance evidence and acceptance before final measurement

Correctness is mandatory; unlimited cost is not automatically acceptable. C03 is a safe reference path, not a claim of optimal warm-cache performance. Do not revert freshness or cross-operation qualification to match an unsafe baseline.

Preregister deterministic fixtures: F0 empty; F1 the unchanged existing acceptance fixture; F2 10,000 distinct 4 KiB files; F3 10,000 identical 1 KiB files; F4 one 256 MiB file; F5 the link/name/metadata fixture; F6 histories of 0, 32 and 256 committed transitions, measuring one additional update, history read and GC without confusing setup cost with operation latency; include fixed small config/manifest metadata changes at an unchanged tree root and tagged-history GC in the registered F6 variants. These sizes are chosen test inputs, not measured results. Record generator version/seed and raw fixture hash. Local stress may add 1 GiB files after capacity check without replacing the mandatory set.

For small fixtures use 3 warmups plus 20 measured paired runs; for F4 use 1 warmup plus 7 measured runs. Record all samples, median, maximum and dispersion; do not sell a p99 from a tiny sample. Larger tail studies require a separately registered sample count. Interleave base/audited/reference/candidate ordering with a recorded seed. Separate new-store capture, warmed-store reuse, hydrate, and any OS-cache control actually achieved. Do not call a cache cold unless that condition was established.

Measure wall time, bytes read/written/hashed where instrumented, actual copy rung, peak memory, metadata/fsync calls, unique versus logical object counts and GC wait after writers quiesce. Selected initial resource targets: streaming buffers at most 1 MiB per active payload worker; no whole-file buffer; bounded payload worker count recorded per run. These are engineering limits, not benchmark observations; metadata storage is separately O(number of entries).

**Two mandatory gates:** (1) SI-00 freezes the method and gathers baseline/capability data. (2) After a correct reference implementing the semantics of EACH measured fixture is available, before its final candidate results are collected (SI-01/02 can calibrate isolated payload capture; F6 history/GC and composite named-version workloads require the integrated SI-03 protocol), the coordinator and owner/reviewer record numeric fixture-specific latency/memory/GC-wait budgets and their justification in `performance-budget.json`. Compare to the correct reference and disclose deltas against the unsafe historical base as context. The implementer cannot approve its own unexplained budget expansion.

The budget record includes reference code/binary hashes, samples, metric/unit/direction, absolute threshold, workload profile, rationale and approving identity. Missing budgets mean BLOCKED_PERFORMANCE; they do not mean unlimited acceptance. Threshold changes after seeing final results require a versioned plan amendment and new measurements. This revision intentionally contains no fabricated baseline or numeric latency budget without hardware evidence.

## 8. C11 — Minimal, verifiable evidence and resume protocol

Store compact evidence at `docs/plans/snapshot-integrity/evidence/SI-NN.md` plus small structured receipts; raw logs remain artifacts with checksums/expiry and a durable summary. No giant transcript, secret, user workload payload or machine-specific required path is committed.

Each receipt must identify:

```yaml
packet: SI-NN
plan_version: '2.2'
status: EVIDENCE_READY
requested_head_sha: actual-head
checkout_sha: actual-tested-commit
checkout_parents: []
source_tree_sha: actual-tree
code_input_fingerprint: hash-of-reviewed-code-tests-lockfile-build-and-workflow-inputs
plan_commit: actual-plan-commit
binary_sha256: actual-built-binary
runner: {os: actual, arch: actual, filesystem: actual, toolchain: actual, profile: actual}
commands: [] # exact argv, cwd, exit, actual named tests and pass/fail/ignored counts
required_test_inventory_sha256: actual-inventory
artifacts: [] # URL, SHA-256, retention, durable summary
negative_controls: [] # mutant patch hash, classification, causal assertion, restored rerun
incident_disposition: actual-or-unresolved
performance_budget_sha256: actual-or-blocked
review: {identity: actual, independent: false, findings: []}
resource_recovery: {} # actual failure profile, phase, headroom estimate, intervention, result
legacy_and_attribution: {} # classified raw/adopted/verified segments and lost-reply outcome
support_and_topology: [] # representation and capability separately; alias/path cases
review_findings: [] # R01-R14, V2-A01-A06 and integrated-review A01-A06; design versus execution status
activation: {} # G-FOUNDATION inert receipt or G-ACTIVATION exact source identity; not production rollout
resource_domains: [] # namespace identity, participants, actual lock and permitted cleanup boundary
residual_limits: []
```

Placeholders above are schema examples, never acceptable results. A small validator checks exact checkout/parents, build-before-run ordering and binary path/hash; nonzero expected named-test execution; required profile/capability rows; artifact presence/checksums; mutant restoration; and matching frozen budget. Cargo exit 0 with every causal test filtered out fails validation.

**Observed aggregator correction (integrated-review A05):** SI-00 must replace the zero-artifact/echo-only path observed in CI run 35158370442 with an actual evidence-validation gate before that check is used. Bootstrap validates the exact required producer/profile artifact inventory, source identity, checksums, schema, finite metrics/units and missing/duplicate rows. It reports incomplete/failure when a required producer skipped or artifacts are absent. Valid baseline evidence is not a no-regression verdict. SI-05 additionally executes the registered numeric budget comparison and retains its inputs/results; an echo or a success step label never satisfies that contract. Missing final budgets block performance acceptance without preventing SI-00 from validating baseline fixtures. E15 deliberately supplies an empty artifact set, missing profile, malformed metric, stale identity and an omitted comparison. The unrelated benchmark-evidence workflow is assessed on its own artifacts; no inference is made from the defective CI aggregate. No workflow is modified by publication of this specification.

A GitHub PR merge checkout is a separate commit; compare its tree/parents with the intended candidate rather than relabeling it the branch head. Later source, test, dependency, build-script or workflow changes invalidate affected evidence. Documentation-only additions may inherit execution evidence only after a reviewed path-diff plus code-input fingerprint proves those inputs unchanged; record both SHAs. Do not demand a self-referential commit hash in its own evidence file.

States: `PLANNED → PREREQUISITES_VERIFIED → READY → DISPATCH_REQUESTED → RUNNING → EVIDENCE_READY → REVIEWED → INTEGRATED → QUALIFIED`, with precise BLOCKED reasons. No assignment/session means no RUNNING. Resume reads live PR, this version, dispatch receipt and issue comments; records exact head and ownership; reconciles changes; then claims only permitted work. No background monitoring or automatic future dispatch is established by this plan.

## 9. R01–R14 design-resolution matrix

These are **planning resolutions**, not proof the corresponding code defects are fixed.

| Review finding | Selected resolution | Package / required evidence |
|---|---|---|
| R01 failed-finalization reuse | C01/C03: ordered readiness receipts, immutable confirmed objects and fresh rewrite of unconfirmed payloads | SI-01; E04 |
| R02 ghost committed history | C05: pending decision phase, complete before/after tuple recovery, guarded consumers | SI-03; E07/E08/E14 |
| R03 stale stat cache | C04: snapshot identity from this invocation's owned bytes | SI-02; E05 |
| R04 hidden GC roots | C06: authoritative refs enumeration, strict family loaders, abort incomplete sweep | SI-03; E11 |
| R05 false parallel independence | C02 and work graph: freeze seam, G-FOUNDATION, ref plus caller same integration | SI-00/01/03; E09/E10 |
| R06 late evidence infrastructure | SI-00 provides and verifies native/CI capability before dependent work | SI-00; platform receipts/E15 |
| R07 ambiguous failure outcomes | C01/C05/C08: explicit commit-decision point, recovery, retention and operation-local effects | SI-03; E07/E08/E13 |
| R08 weak temporal/mutant oracle | Experiment recipes, nonblocking contender proof and explicit mutant dispositions | SI-04; E01–E22 |
| R09 undefined tree fidelity | C07 domain and independent comparator; preserve-or-reject profiles | SI-02/03; E12 |
| R10 active readers | C07 per-materialization lease, explicit untag and bisect boundaries | SI-03; E13 |
| R11 ENOENT over-attribution | C09 diagnostic/control matrix and honest bounded disposition | SI-00/01/05; E16 |
| R12 unbounded performance acceptance | C10 baseline, fixed methodology and preregistered numeric budget gate | SI-00/05; budget/measurement receipts |
| R13 incomplete impact map | SI-00 caller/root inventory; SI-03 owns actual consumers together | SI-00/03; E14 |
| R14 weak evidence association | C11 exact checkout/binary/test validation, negative evidence fixtures | SI-00/05; E15 |

### Second review: V2-A01–V2-A06 planning dispositions

No row below is a claim of code remediation or native execution. The previously reviewed base remains v2.0; this revision needs its own acceptance.

| Finding | Selected decision | Ownership / axioms / required witness |
|---|---|---|
| V2-A01 named OCI hybrid state | Fixed three-component NamedVersion; same pending descriptor gains PREPARED/COMMIT_DECIDED; existing history gains explicit tuple envelopes; all named readers/writers participate | SI-00/03, SC03.4/QS03.4/CC03.5/DOD03.4/INV03.4; E17 |
| V2-A02 recovery without resources | Conditional progress with RecoveryBlockedResources, EX-only proven scratch reaping and safe operator headroom intervention; no unsafe full GC or new reserve | SI-00/01/03/05, C13; their five relevant axiom sections; E18 |
| V2-A03 legacy interior ambiguity | Raw history is LegacyUnverified, labeled read-only inspection and explicit adopted baseline; no default navigation across uncertified history | SI-00/03/04, I14; E19 |
| V2-A04 Windows representation | LMF1 unchanged; a manifest-derived direct in-tree link subset is allowed; ambiguous classes rejected independently of privilege | SI-00/02/03/05, C07/I09; E20 |
| V2-A05 lost request identity | AttributionUnknown independent from store health/recovery; no auto replay and no new request ledger | SI-03/04/05, C01/C08/I14; E21 |
| V2-A06 overlapping namespaces | Public disjointness, canonical/handle ancestry, preflight before prohibited writes and bounded internal ownership exceptions | SI-00/02/03, C12/I09; E22 |

The review's two non-finding observations are also incorporated: F6 uses a semantically complete SI-03 reference, and schema/caller review must justify the maintenance cost of the EXISTING protocol planes. The tuple/history extension is not disguised as unchanged format. No permanent protocol is added for resource headroom, request deduplication, link type or path disjointness.

### Integrated review A01–A06 — targeted amendment, not new runtime evidence

| Finding | Selected planning response | Owner / existing acceptance witness |
|---|---|---|
| A01 shared scratch versus Store locks | C02 resource-domain table; shared cache has its own short EX sections; C13 reaper uses that actual domain | SI-00/01/02/03; E18/E22, two Stores plus standalone cache writer |
| A02 lexical parent across symlink | C12 native anchored component resolution or explicit rejection; same validated/used object | SI-02/03; E22 distinct-target and trailing-slash controls |
| A03 intermediate protocol activation | Additive inert SI-01/02, G-FOUNDATION is not product enablement; final coordinated SI-03 slice establishes G-ACTIVATION | SI-00/01/03/04/05; public entrypoint lease/caller coverage, exact activation SHA |
| A04 pending without current | C06 independent strict pending pre-scan before root collection/sweep | SI-03/04; E08/E11, GC immediately after restart before recovery |
| A05 benchmark false assurance | C11 bootstrap artifact validation plus real SI-05 numeric comparison; preserve historical CI failure context | SI-00/05; E15 and budget receipts, not an echo |
| A06 native issue hierarchy/dependencies/Project | Existing campaign and issues are retained; only verified native mutations count | Coordinator; current DISPATCH.md states completed/blocked facts, not runtime qualification |

This amendment preserves six WPs, all five axioms per WP, existing criterion IDs and E01–E22. It does not execute bootstrap, accept ADRs, activate/migrate any store or close implementation findings. Earlier 278 abstract scenarios remain historical model evidence, not newly executed or sufficient proof of these refinements.

## 10. Exit decision

Design review may accept this specification without asserting runtime correctness. Implementation cannot be dispatched merely because R01–R14 and V2-A01–V2-A06 have design responses. SI-00's ADR/compatibility, platform, seam and evidence prerequisites must be real; future execution must be explicitly authorized.

Campaign qualification requires all six packages' Success Criteria, Quality Standards, Completeness Criteria, DoD and Invariants satisfied; all mandatory C08/E-rows, C12 topology and C13 resource-recovery profiles present; all six V2-A and integrated-review A01–A05 implementation obligations supported, including G-ACTIVATION; native tracking A06 reported separately; no unreviewed causal survivor or integrity failure; C09/C10 dispositions accepted; and current-head evidence validated under C11. Main merge/release remains the owner's separate decision.

## Primary sources and code anchors

Design decisions above are proposed here; sources document the underlying constraints, not a claim that this protocol is already proven.

- [Baseline snapshot publisher](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-index/src/index/snapshot.rs), [scan](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-index/src/index/scan.rs), [index codec](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-index/src/index/codec.rs).
- [CAS](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-store/src/store/cas/mod.rs), [refs](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-store/src/store/refs.rs), [GC](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-index/src/index/gc.rs), [hydrate](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-index/src/index/hydrate.rs), [timeaxis](https://github.com/gmhelmold/hugr-lightr/blob/e4a53417f6fe7da8c4f44908af9525536443d0fa/crates/lightr-index/src/index/timeaxis.rs).
- P1: [Rust File synchronization/opening](https://doc.rust-lang.org/std/fs/struct.File.html).
- P2: [Microsoft FlushFileBuffers handle rights and return semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers).
- P3: [Linux fsync file versus directory barriers](https://man7.org/linux/man-pages/man2/fsync.2.html).
- P4: [Rebello et al., Can Applications Recover from fsync Failures?, USENIX ATC 2020](https://www.usenix.org/conference/atc20/presentation/rebello).
- P5: [Microsoft CreateSymbolicLinkW: directory/file flags and privilege are separate](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createsymboliclinkw). The Windows subset is a chosen support policy, not a Microsoft guarantee for this manifest format.
- P6: [Linux path_resolution(7): native component/symlink/parent semantics](https://man7.org/linux/man-pages/man7/path_resolution.7.html).
- P7: [Linux flock(2): lock identity and open-file-description semantics](https://man7.org/linux/man-pages/man2/flock.2.html). These references constrain native witnesses; the resource-domain protocol above remains a design requiring native qualification.
- [Rust rename platform behavior](https://doc.rust-lang.org/std/fs/fn.rename.html), [SQLite atomic-commit explanation](https://www.sqlite.org/atomiccommit.html), [Git Racy Git](https://git-scm.com/docs/racy-git). These are constraints/precedents, not mandates to replace the store with another system.
