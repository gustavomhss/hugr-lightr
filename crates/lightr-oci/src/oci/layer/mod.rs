//! Layer blob representation and apply_layers core.

#[cfg_attr(not(unix), allow(dead_code))]
mod apply;
#[cfg(unix)]
mod unix;

#[cfg(unix)]
use apply::{apply_ops, collect_ops};
use flate2::read::GzDecoder;
use lightr_core::{LightrError, Result};
use lightr_store::Store;
use std::{
    fs,
    io::{self, BufReader, Read},
    path::PathBuf,
};

// ─────────────────────────────────────────────────────────────────────────────
// Layer blob: in-memory bytes or a temp file path (for pull)
// ─────────────────────────────────────────────────────────────────────────────

#[cfg_attr(not(unix), allow(dead_code))]
pub(super) enum LayerBlob {
    /// The layer data lives at this path (owned by the caller's TempDirGuard).
    File(PathBuf),
    /// The layer data is a slice from a larger buffer (docker-save style).
    Bytes(Vec<u8>),
}

#[cfg_attr(not(unix), allow(dead_code))]
impl LayerBlob {
    /// Open a streaming `Read` over the layer, auto-detecting gzip by magic bytes.
    ///
    /// # Streaming design (no whole-layer Vec)
    ///
    /// For `File`: open → `BufReader` → read the first 2 bytes for the gzip magic
    /// (`0x1f 0x8b`). Those 2 bytes are chained back to the rest of the file via
    /// `io::Cursor::new([b0,b1]).chain(rest)` so the caller sees a complete stream.
    /// If gzip is detected the combined reader is wrapped in `flate2::read::GzDecoder`;
    /// otherwise it is returned as-is. At no point is the full file read into RAM.
    ///
    /// For `Bytes`: the same peek-and-chain logic is applied to an `io::Cursor` over
    /// the in-memory slice; behaviour is identical, no extra allocation.
    pub(super) fn open_reader(&self) -> io::Result<Box<dyn Read + '_>> {
        match self {
            LayerBlob::File(p) => {
                let file = fs::File::open(p)?;
                let mut reader = BufReader::new(file);
                // Peek the first 2 bytes to detect gzip magic.
                let mut magic = [0u8; 2];
                let n = reader.read(&mut magic)?;
                // Chain the consumed bytes back so the tarball sees a complete stream.
                let prefix = io::Cursor::new(magic[..n].to_vec());
                let full: Box<dyn Read> = Box::new(prefix.chain(reader));
                if n == 2 && magic[0] == 0x1f && magic[1] == 0x8b {
                    Ok(Box::new(GzDecoder::new(full)))
                } else {
                    Ok(full)
                }
            }
            LayerBlob::Bytes(b) => {
                let mut cursor = io::Cursor::new(b.as_slice());
                let mut magic = [0u8; 2];
                let n = cursor.read(&mut magic)?;
                let prefix = io::Cursor::new(magic[..n].to_vec());
                let full: Box<dyn Read> = Box::new(prefix.chain(cursor));
                if n == 2 && magic[0] == 0x1f && magic[1] == 0x8b {
                    Ok(Box::new(GzDecoder::new(full)))
                } else {
                    Ok(full)
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// layer_timeout_secs — per-call deadline config
// ─────────────────────────────────────────────────────────────────────────────

/// Parse the per-call wall-clock deadline for `apply_layers`.
///
/// Default: 600 s.  Override via `LIGHTR_LAYER_TIMEOUT_SECS` (any non-integer
/// or value ≤ 0 silently falls back to the default).
#[cfg_attr(not(unix), allow(dead_code))]
pub(super) fn layer_timeout_secs() -> u64 {
    const DEFAULT_TIMEOUT_SECS: u64 = 600;
    std::env::var("LIGHTR_LAYER_TIMEOUT_SECS")
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|&v| v > 0)
        .unwrap_or(DEFAULT_TIMEOUT_SECS)
}

// ─────────────────────────────────────────────────────────────────────────────
// apply_layers — private shared core (driver)
// ─────────────────────────────────────────────────────────────────────────────

/// Apply `blobs` in order into `tempdir`, honouring OCI whiteouts and path
/// safety. Archive traversal rejects the entire import.
///
/// Each blob may be gzip-compressed (auto-detected by magic bytes 0x1f 0x8b)
/// or a plain tar archive.
///
/// # FIX 3 + 4: Intra-layer whiteout ordering
///
/// OCI spec: whiteout entries in a layer refer to the *parent* layer's
/// contents. Within a single layer we process ALL deletes (whiteouts) before
/// any additions so that a file added AND whited out in the same layer ends up
/// absent (OCI parent-ref semantics).
///
/// Implementation: two-pass per layer.
///   Pass 1 (`collect_ops`) — collect dirs to create, whiteouts to apply,
///             and pending file/symlink/hardlink writes.
///   Between passes — apply directory creates + all whiteouts.
///   Pass 2 (`apply_ops`) — write regular files and symlinks.
///   After pass 2 — resolve hardlinks (FIX 5).
#[cfg(unix)]
pub(super) fn apply_layers(blobs: &[LayerBlob]) -> Result<LayerStage> {
    let mut fs = unix::UnixLayerFs::new()?;
    let timeout = layer_timeout_secs();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(timeout);
    let mut entry_count: u64 = 0;

    for blob in blobs {
        // Open a streaming reader over the blob.
        //
        // `open_reader` peeks the first 2 bytes for gzip magic (0x1f 0x8b), chains
        // them back, and wraps in `flate2::read::GzDecoder` if compressed — all
        // without reading the full layer into a Vec.  The `tar` crate's `Archive`
        // accepts any `impl Read`, so decompression and entry parsing happen
        // chunk-by-chunk through a bounded I/O buffer.
        let reader = blob.open_reader().map_err(LightrError::Io)?;
        let mut archive = tar::Archive::new(reader);

        // ── Pass 1: collect all operations ───────────────────────────────────
        //
        // We parse the entire layer tar into three buckets:
        //   `dirs`      — directory entries (create first, before any writes)
        //   `whiteouts` — (parent_in_temp, whiteout_name or None for opaque)
        //   `pending`   — regular files, symlinks, hardlinks
        //
        // FIX 3: all whiteout operations execute before any file writes.
        // FIX 4: opaque whiteout clears the dir in the accumulated tree and
        //        creates it if absent.
        let (ops, whited_out_paths) =
            collect_ops(&mut archive, deadline, &mut entry_count, timeout)?;

        // ── Pass 2: apply dirs → whiteouts → files → hardlinks ───────────────
        apply_ops(&mut fs, &ops, &whited_out_paths)?;
    }

    Ok(LayerStage(fs))
}

#[cfg(unix)]
pub(super) struct LayerStage(unix::UnixLayerFs);
#[cfg(unix)]
impl LayerStage {
    fn snapshot_source(&self) -> Result<(unix::UnixSnapshotSource, lightr_core::Manifest)> {
        self.0.snapshot_source()
    }

    fn cleanup(&mut self) -> Result<()> {
        self.0.cleanup()
    }
}

#[cfg(not(unix))]
#[allow(dead_code)]
pub(super) struct LayerStage;
#[cfg(not(unix))]
#[allow(dead_code)]
impl LayerStage {
    fn path(&self) -> &std::path::Path {
        unreachable!("unsupported OCI layer apply cannot create a stage")
    }
}
#[cfg(not(unix))]
#[allow(dead_code)]
pub(super) fn apply_layers(_blobs: &[LayerBlob]) -> Result<LayerStage> {
    Err(LightrError::Unsupported(
        "OCI layer apply has no qualified named-handle backend on this platform".into(),
    ))
}

// ─────────────────────────────────────────────────────────────────────────────
// apply_and_snapshot — create a fresh tempdir, apply blobs, snapshot
// ─────────────────────────────────────────────────────────────────────────────

/// Create private descriptor-anchored staging, apply blobs, snapshot, return report.
#[cfg(unix)]
#[cfg_attr(not(test), allow(dead_code))]
pub(super) fn apply_and_snapshot(
    blobs: Vec<LayerBlob>,
    layer_count: u64,
    store: &Store,
    name: &str,
) -> Result<super::model::ImportReport> {
    let mut stage = apply_layers(&blobs)?;
    let (source, manifest) = stage.snapshot_source()?;
    let pending = lightr_index::prepare_snapshot_from_source(&source, store, name, manifest)?;
    stage.cleanup()?;
    let report = pending.commit()?;

    Ok(super::model::ImportReport {
        name: name.to_string(),
        root: report.root,
        layers: layer_count,
        files: report.files,
    })
}

#[cfg(not(unix))]
#[allow(dead_code)]
pub(super) fn apply_and_snapshot(
    _blobs: Vec<LayerBlob>,
    _layer_count: u64,
    _store: &Store,
    _name: &str,
) -> Result<super::model::ImportReport> {
    Err(LightrError::Unsupported(
        "OCI layer apply has no qualified named-handle backend on this platform".into(),
    ))
}

/// OCI import publishes captured config, manifest record, and snapshot ref as
/// one Store envelope after every body and tree object is ready.
#[cfg(unix)]
pub(super) fn apply_and_publish_image(
    blobs: Vec<LayerBlob>,
    layer_count: u64,
    store: &Store,
    name: &str,
    config: &[u8],
    image_manifest: &lightr_store::ImageManifestRecord,
) -> Result<super::model::ImportReport> {
    let mut stage = apply_layers(&blobs)?;
    let (source, manifest) = stage.snapshot_source()?;
    let pending = lightr_index::prepare_snapshot_from_source(&source, store, name, manifest)?;
    stage.cleanup()?;
    let report = pending
        .commit_with(|rec| store.publish_image_ref(rec, Some(config), Some(image_manifest)))?;
    Ok(super::model::ImportReport {
        name: name.to_string(),
        root: report.root,
        layers: layer_count,
        files: report.files,
    })
}

#[cfg(not(unix))]
pub(super) fn apply_and_publish_image(
    _blobs: Vec<LayerBlob>,
    _layer_count: u64,
    _store: &Store,
    _name: &str,
    _config: &[u8],
    _image_manifest: &lightr_store::ImageManifestRecord,
) -> Result<super::model::ImportReport> {
    Err(LightrError::Unsupported(
        "OCI layer apply has no qualified named-handle backend on this platform".into(),
    ))
}
