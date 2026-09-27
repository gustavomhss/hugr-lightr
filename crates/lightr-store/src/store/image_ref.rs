//! LOCIE1 per-ref OCI publication envelopes.

use super::cas::{get_bytes, put_bytes};
use super::imgmeta::{
    codec::{decode_manifest_record, encode_manifest_record},
    ImageManifestRecord,
};
use super::refs;
use lightr_core::{Digest, LightrError, RefRecord, Result};
use std::fs;
use std::path::Path;

const MAGIC: &[u8; 8] = b"\0\0LOCIE1";
const VERSION: u32 = 1;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PreparedImageRef {
    pub config: Option<Digest>,
    pub manifest: Option<Digest>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImageRef {
    pub record: RefRecord,
    pub config: Option<Vec<u8>>,
    pub manifest: Option<ImageManifestRecord>,
}

#[derive(Clone, Debug)]
pub(crate) struct Envelope {
    pub record: RefRecord,
    pub prepared: PreparedImageRef,
}

fn malformed(reason: impl Into<String>) -> LightrError {
    LightrError::InvalidManifest(format!("malformed LOCIE1 envelope: {}", reason.into()))
}

fn take<'a>(bytes: &'a [u8], pos: &mut usize, n: usize) -> Result<&'a [u8]> {
    let end = pos
        .checked_add(n)
        .filter(|end| *end <= bytes.len())
        .ok_or_else(|| malformed("truncated frame"))?;
    let out = &bytes[*pos..end];
    *pos = end;
    Ok(out)
}

fn digest(bytes: &[u8]) -> Digest {
    let mut out = [0; 32];
    out.copy_from_slice(bytes);
    Digest(out)
}

pub(super) fn decode_envelope(bytes: &[u8]) -> Result<Option<Envelope>> {
    if !bytes.starts_with(MAGIC) {
        return Ok(None);
    }
    let mut pos = MAGIC.len();
    let version = u32::from_le_bytes(take(bytes, &mut pos, 4)?.try_into().unwrap());
    if version != VERSION {
        return Err(malformed(format!("unknown version {version}")));
    }
    let rec_len = u32::from_le_bytes(take(bytes, &mut pos, 4)?.try_into().unwrap()) as usize;
    let record =
        RefRecord::decode(take(bytes, &mut pos, rec_len)?).map_err(|e| malformed(e.to_string()))?;
    lightr_core::validate_ref_name(&record.name).map_err(|e| malformed(e.to_string()))?;
    let config = match take(bytes, &mut pos, 1)?[0] {
        0 => None,
        1 => Some(digest(take(bytes, &mut pos, 32)?)),
        _ => return Err(malformed("invalid config-present flag")),
    };
    let manifest = match take(bytes, &mut pos, 1)?[0] {
        0 => None,
        1 => Some(digest(take(bytes, &mut pos, 32)?)),
        _ => return Err(malformed("invalid manifest-present flag")),
    };
    if pos != bytes.len() {
        return Err(malformed("trailing bytes"));
    }
    Ok(Some(Envelope {
        record,
        prepared: PreparedImageRef { config, manifest },
    }))
}

fn encode_envelope(record: &RefRecord, prepared: &PreparedImageRef) -> Result<Vec<u8>> {
    lightr_core::validate_ref_name(&record.name)?;
    let record = record.encode();
    let len = u32::try_from(record.len()).map_err(|_| malformed("ref record too large"))?;
    let mut out = Vec::with_capacity(MAGIC.len() + 4 + 4 + record.len() + 66);
    out.extend_from_slice(MAGIC);
    out.extend_from_slice(&VERSION.to_le_bytes());
    out.extend_from_slice(&len.to_le_bytes());
    out.extend_from_slice(&record);
    for pointer in [&prepared.config, &prepared.manifest] {
        match pointer {
            Some(digest) => {
                out.push(1);
                out.extend_from_slice(&digest.0);
            }
            None => out.push(0),
        }
    }
    Ok(out)
}

fn read_envelope(root: &Path, name: &str) -> Result<Option<Envelope>> {
    lightr_core::validate_ref_name(name)?;
    let path = refs::ref_path(root, &lightr_core::ref_key(name));
    if !path.exists() {
        return Ok(None);
    }
    let Some(envelope) = decode_envelope(&fs::read(path)?)? else {
        return Ok(None);
    };
    if envelope.record.name != name {
        return Err(malformed("ref name does not match storage key"));
    }
    Ok(Some(envelope))
}

fn require_body(root: &Path, digest: Digest) -> Result<Vec<u8>> {
    get_bytes(root, &digest)
        .map_err(|e| malformed(format!("missing or invalid pointed-to CAS body: {e}")))
}

pub(super) fn validate_bodies(root: &Path, envelope: &Envelope) -> Result<()> {
    for digest in [envelope.prepared.config, envelope.prepared.manifest]
        .into_iter()
        .flatten()
    {
        require_body(root, digest)?;
    }
    Ok(())
}

pub fn image_ref_get(root: &Path, name: &str) -> Result<Option<ImageRef>> {
    let Some(envelope) = read_envelope(root, name)? else {
        let Some(record) = refs::ref_get(root, name)? else {
            return Ok(None);
        };
        return Ok(Some(ImageRef {
            config: super::imgmeta::image_config_get(root, name)?,
            manifest: super::imgmeta::image_manifest_get(root, name)?,
            record,
        }));
    };
    let config = envelope
        .prepared
        .config
        .map(|d| require_body(root, d))
        .transpose()?;
    let manifest = envelope
        .prepared
        .manifest
        .map(|d| {
            let body = require_body(root, d)?;
            decode_manifest_record(&body)
                .map_err(|e| malformed(format!("invalid manifest body: {e}")))
        })
        .transpose()?;
    Ok(Some(ImageRef {
        record: envelope.record,
        config,
        manifest,
    }))
}

pub fn publish_image_ref(
    root: &Path,
    rec: &RefRecord,
    config: Option<&[u8]>,
    manifest: Option<&ImageManifestRecord>,
) -> Result<()> {
    let _guard = super::lock::write_guard(root)?;
    let prepared = PreparedImageRef {
        config: config.map(|body| put_bytes(root, body)).transpose()?,
        manifest: manifest
            .map(|body| put_bytes(root, &encode_manifest_record(body)))
            .transpose()?,
    };
    publish_prepared_image_ref(root, rec, prepared)
}

pub fn publish_prepared_image_ref(
    root: &Path,
    rec: &RefRecord,
    prepared: PreparedImageRef,
) -> Result<()> {
    let _guard = super::lock::write_guard(root)?;
    for digest in [prepared.config, prepared.manifest].into_iter().flatten() {
        require_body(root, digest)?;
    }
    if let Some(digest) = prepared.manifest {
        decode_manifest_record(&require_body(root, digest)?)
            .map_err(|e| malformed(format!("invalid manifest body: {e}")))?;
    }
    refs::ref_put_encoded(root, rec, &encode_envelope(rec, &prepared)?)
}

pub(crate) fn envelope_for(root: &Path, name: &str) -> Result<Option<Envelope>> {
    read_envelope(root, name)
}

/// Return every CAS body retained by current LOCIE1 envelopes. Unlike legacy
/// sidecars, an envelope is authoritative: an unreadable body makes GC stop
/// before sweep rather than reclaiming a still-referenced closure.
pub(crate) fn envelope_reachable_blobs(root: &Path) -> Result<Vec<Digest>> {
    let mut out = Vec::new();
    for name in refs::list_refs(root)? {
        let Some(envelope) = envelope_for(root, &name)? else {
            continue;
        };
        if let Some(digest) = envelope.prepared.config {
            require_body(root, digest)?;
            out.push(digest);
        }
        if let Some(digest) = envelope.prepared.manifest {
            let body = require_body(root, digest)?;
            let record = decode_manifest_record(&body)
                .map_err(|e| malformed(format!("invalid manifest body: {e}")))?;
            out.push(digest);
            out.extend(
                record
                    .descriptors
                    .into_iter()
                    .map(|descriptor| descriptor.digest),
            );
        }
    }
    Ok(out)
}

#[cfg(test)]
#[path = "image_ref_tests.rs"]
mod tests;
