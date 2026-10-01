//! Retained snapshot owner. Compose must hold this object, never an engine session.

use lightr_core::{LightrError, Result};
use lightr_engine::{Engine, ExecSpec, ResumedInstance, SuspendResume, SuspendedArtifact};
use std::path::{Path, PathBuf};

/// Owns engine and its snapshot until explicit resume or cleanup.
pub struct SuspensionOwner {
    engine: Box<dyn Engine>,
    artifact: SuspendedArtifact,
    artifact_dir: PathBuf,
}

/// Non-secret suspended identity safe for compose state and receipts.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SuspendedIdentity {
    pub instance_id: String,
    pub artifact_sha256: String,
}

impl SuspensionOwner {
    /// Suspend before listener bind. Unsupported remains typed data for caller.
    pub fn suspend(
        engine: Box<dyn Engine>,
        spec: &ExecSpec,
        stack_dir: &Path,
        service: &str,
    ) -> Result<std::result::Result<Self, SuspendResume>> {
        let artifact_dir = stack_dir.join("services").join(service).join("snapshot");
        std::fs::create_dir_all(&artifact_dir).map_err(LightrError::Io)?;
        match engine.suspend(spec, &artifact_dir)? {
            SuspendResume::Suspended(artifact) => Ok(Ok(Self {
                engine,
                artifact,
                artifact_dir,
            })),
            unsupported @ SuspendResume::Unsupported { .. } => {
                let _ = std::fs::remove_dir_all(&artifact_dir);
                Ok(Err(unsupported))
            }
        }
    }

    /// Call only after lazy listener consumed its accepted request payload.
    pub fn resume(&self) -> Result<ResumedInstance> {
        self.engine.resume(&self.artifact)
    }

    pub fn identity(&self) -> SuspendedIdentity {
        SuspendedIdentity {
            instance_id: self.artifact.instance_id.clone(),
            artifact_sha256: self.artifact.artifact_sha256.clone(),
        }
    }

    pub fn guest_ip(&self) -> Result<String> {
        let ip = std::fs::read_to_string(
            self.artifact
                .rootfs()
                .join(lightr_init::IP_FILE.trim_start_matches('/')),
        )
        .map_err(LightrError::Io)?;
        let ip = ip.trim().to_string();
        if ip.is_empty() {
            return Err(LightrError::InvalidRef(
                "suspended VZ guest has no DHCP IP proof".into(),
            ));
        }
        Ok(ip)
    }

    /// Removes snapshot/gate artifacts after retained engine is dropped.
    pub fn cleanup(self) -> Result<()> {
        self.engine.teardown();
        std::fs::remove_dir_all(&self.artifact_dir).map_err(LightrError::Io)
    }
}

impl Drop for SuspensionOwner {
    fn drop(&mut self) {
        self.engine.teardown();
        let _ = std::fs::remove_dir_all(&self.artifact_dir);
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn suspension_owner_keeps_artifact_private_and_resume_accepts_no_token() {
        let source = include_str!("suspend.rs");
        let owner = source.split("#[cfg(test)]").next().unwrap();
        assert!(!owner.contains("pub fn artifact("));
        assert!(owner.contains("pub fn resume(&self) -> Result<ResumedInstance>"));
        assert!(owner.contains("self.engine.resume(&self.artifact)"));
    }
}
