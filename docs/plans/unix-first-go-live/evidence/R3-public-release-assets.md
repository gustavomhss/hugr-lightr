# R3 Actual Public Release Assets: Native Receipt

**Status: PASS for native Linux x86_64/macOS arm64 byte installation**, [owner accepted][accepted] under [execution authority][execution].
[400899741][release] remains `draft=true`, `published_at=null`; no crate publication/promotion authorization.
**VZ NOT EXECUTED/unvalidated; full R2 incomplete**.

## Product, verifier, and execution identities

Product/producer workflow: `47f02795d0884956c4755254b5f6fc377a5938b5`, version `0.1.1`, Rust `1.96.0`.
Annotated unsigned `v0.1.1` object `ab042ab801f0bba462385c4c4fd47ac5f60c0866` peels to that source. [Producer 36850231990][producer], attempt 1, completed/success.
Independent [consumer 36883638341][consumer], attempt 1, completed/success at
`2026-10-01T15:22:42Z`; verifier/workflow `b0aabc450eab83ee844c29273b8203e5fd84365f`.
That verifier and this documentation commit are not qualified product source.

| Target / native job | Runner ID | Worker ID | Image |
| --- | --- | --- | --- |
| [macOS arm64 / 110441356788][mac-job] | 1000044303 | 3a166e0d-2b76-4d54-987c-9aed4e56f156 | macos-14-arm64 / 20260831.0302.1 |
| [Linux x86_64 / 110441356160][linux-job] | 1000044302 | 25938cbe-6f7c-49d6-9a82-f9b0b74c456f | ubuntu-24.04 / 20260927.320.1 |

Mac: Darwin arm64, macOS `14.8.9` / `23J631`, `hw.optional.arm64=1`, model
`VirtualMac2,1`; Linux: Ubuntu `24.04.5`, kernel `6.17.0-1022-azure`, x86_64.
Physical CPU brands/VM hardware UUIDs were not recorded. Mac **29 commands**,
Linux **21 commands**, all exit `0`; zero required consumer skips. Each recorded
transport made **11 `gh api --method GET` requests** using the real GitHub App token:
job logs show **Contents: write, Actions: read, Metadata: read**. Live draft/producer/
artifact/asset reads succeeded. This role supplies draft visibility, not crate rights.

Historical [36877718655][failed] failed private-draft GET with `contents: read`
(verifier `7ecbd6408dd248b70dbfaaca6a0146d559760831`); its diagnostics remain preserved.
Reviewed [#283][repair] explicitly repaired the independent verifier role. New
success is not a retry of failed code, a public draft, or a producer-source change.
RC **86 OCI + 8 exact witnesses** per target remain separate evidence in [R0](R0.md);
neither public producer nor consumer reran that suite. No CLI rebuild/re-sign occurred.

## Immutable byte chain and retention

Each producer ZIP matched API digest and contained exactly its target tarball and original `.sha256`.
Consumer downloaded exact draft asset IDs; both files matched ZIP bytes. Five unique asset IDs/inventory remained unchanged.

| Producer ZIP / target | ZIP SHA-256 | API expiry UTC |
| --- | --- | --- |
| [11156140739 / macOS][mac-producer-zip] | `48d833e61d6ba181127d2f763f492eb2937df2746e877f11563d66dc19b2d4b8` | 2026-10-02T10:45:47Z |
| [11155582652 / Linux][linux-producer-zip] | `abb9e794a310f3ab14472e7bee4ad37bf1bfe81687a4005c392ccd0701ece0a3` | 2026-10-02T10:44:57Z |

| Draft asset / immutable API ID | SHA-256 of downloaded bytes |
| --- | --- |
| `lightr-0.1.1-darwin-arm64-unsigned.tar.gz` / [603105608](https://api.github.com/repos/gmhelmold/hugr-lightr/releases/assets/603105608) | `73af74ca490a9c600cf12271162005ef837d9b89f3dc83cc7c7368edbd7aca0d` |
| `lightr-0.1.1-darwin-arm64-unsigned.tar.gz.sha256` / [603105607](https://api.github.com/repos/gmhelmold/hugr-lightr/releases/assets/603105607) | `39dc56f100de19f017bb400e8a534fc8f99d905e748b39607905491037e0faa1` |
| `lightr-0.1.1-linux-x86_64.tar.gz` / [603105609](https://api.github.com/repos/gmhelmold/hugr-lightr/releases/assets/603105609) | `b8e83623b413a36b847cb4417fb623b9ab37500d5cab71bc9299fa2c2f38a6ca` |
| `lightr-0.1.1-linux-x86_64.tar.gz.sha256` / [603105606](https://api.github.com/repos/gmhelmold/hugr-lightr/releases/assets/603105606) | `53ad88f7533b805f9afdc30fd3a26501e016849ded0772b075a4acd5961c5339` |
| `SHA256SUMS` / [603105603](https://api.github.com/repos/gmhelmold/hugr-lightr/releases/assets/603105603) | `df42e970e55a21f684a607090ee688381efa00a540b1a16c0570591fc0c99a1e` |

Individual checksums were exact `<hash>  <filename>\n`; aggregate contained exactly
the two canonical tarball records and matching target hashes. Each tar held only
regular `lightr`, mode `0755`. Archive-member binary hashes equalled installed bytes
before and after version/help; cleanup ran in `finally` and asserted absent HOME.

| Target | Binary SHA-256 (archive / installed before and after smoke) | Receipt JSON SHA-256 |
| --- | --- | --- |
| macOS | `fe1bddbd4bb83cb79de0082231f229cb20e4e45cf588f1186a15c188fbf170f9` | `74ca8276f58cb1015887bd01fc3e21577e03faa1d7be71db280a27cfe4987a27` |
| Linux | `11917005d6fe0cdb7c97d5779743c9ebd96f2bd97cbfe73f4a74728889f9a2ea` | `5a4319996b190700cc5fe1f16cffad5803a45d40565875e833405d9319935ae4` |

## Native commands and inspection

Expanded argv below exited `0`; checksum cwd was each checkout's `public-release-install/`, other cwd the verifier checkout.
Smoke used isolated fresh HOME, `LC_ALL=C`; children received no API credential.

```bash
shasum -a 256 -c lightr-0.1.1-darwin-arm64-unsigned.tar.gz.sha256
tar -xzf /Users/runner/work/hugr-lightr/hugr-lightr/public-release-install/lightr-0.1.1-darwin-arm64-unsigned.tar.gz -C /Users/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-egqnhkkt
install -m 755 /Users/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-egqnhkkt/lightr /Users/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-egqnhkkt/.local/bin/lightr
/Users/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-egqnhkkt/.local/bin/lightr --version
/Users/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-egqnhkkt/.local/bin/lightr --help
rm -rf /Users/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-egqnhkkt
sha256sum -c lightr-0.1.1-linux-x86_64.tar.gz.sha256
tar -xzf /home/runner/work/hugr-lightr/hugr-lightr/public-release-install/lightr-0.1.1-linux-x86_64.tar.gz -C /home/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-sa0tl71t
install -m 755 /home/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-sa0tl71t/lightr /home/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-sa0tl71t/.local/bin/lightr
/home/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-sa0tl71t/.local/bin/lightr --version
/home/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-sa0tl71t/.local/bin/lightr --help
rm -rf /home/runner/work/hugr-lightr/hugr-lightr/public-release-install/fresh-home-sa0tl71t
```

Both versions: **`lightr 0.1.1 (47f0279, 2026-10-01)`**; help:
`Usage: lightr [OPTIONS] <COMMAND>`; checksum outputs named each tarball `: OK`.
Mac `file`/`lipo -archs` proved arm64-only Mach-O; `codesign --verify --strict`
passed, parsed virtualization entitlement was **BOOL true**, `codesign -dv --verbose=4`
reported `Signature=adhoc`: **unsigned; no Developer ID; not notarized**. Linux
inspection checked the ELF64 little-endian x86_64 header. No VZ execution occurred.

## Raw receipt provenance and limits

Proof ZIPs matched API digests; retention expires October 31 (UTC below):

| Proof ZIP / target | ZIP SHA-256 | Expires |
| --- | --- | --- |
| [11173190325 / macOS][mac-proof] | `063d38db1bf62ad4882c9b677c3e765de6284601957f1bad87ac9b009bac3a8c` | 2026-10-31T15:22:37Z |
| [11173310173 / Linux][linux-proof] | `60364716e5bd0d95186ce8810e90c546ddc3b2cfc46f92785e69eebbaac3b67f` | 2026-10-31T15:22:32Z |

ZIP-root `receipt.json`, `commands.json` retain all argv/exit/output and available cwd/HOME fields; Mac `18.log`–`28.log`, Linux `15.log`–`20.log` retain native phases.
Local raw bundle: `/var/folders/lt/z11pyzhj0m17vn798jkk69hh0000gn/T/opencode/lightr-public-consumer-36883638341.S4Mmjj`
(`mac-proof/`, `linux-proof/`, API metadata, verification and original hash manifests).
Producer and failed-consumer sibling bundles `lightr-public-producer-36850231990.GPdHpE`
and `lightr-public-consumer-36877718655.KQyuhC` remain preserved. Release-ID GET is
authenticated draft access; draft tag/browser URLs are not public-release evidence.
Snapshot body labels the draft unpublished and VZ unvalidated. [#113](https://github.com/gmhelmold/hugr-lightr/issues/113) stays open; only its 0.1.1 publication predecessor is waived.
Publish-new/update scopes remain UNVERIFIED; [publisher gates](R4-publisher-preflight.md) still block publication/promotion.

[accepted]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5934996357
[execution]: https://github.com/gmhelmold/hugr-lightr/issues/187#issuecomment-5929619780
[release]: https://api.github.com/repos/gmhelmold/hugr-lightr/releases/400899741
[producer]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36850231990
[consumer]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36883638341
[mac-job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36883638341/job/110441356788
[linux-job]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36883638341/job/110441356160
[failed]: https://github.com/gmhelmold/hugr-lightr/actions/runs/36877718655
[repair]: https://github.com/gmhelmold/hugr-lightr/pull/283
[mac-producer-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11156140739/zip
[linux-producer-zip]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11155582652/zip
[mac-proof]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11173190325/zip
[linux-proof]: https://api.github.com/repos/gmhelmold/hugr-lightr/actions/artifacts/11173310173/zip
