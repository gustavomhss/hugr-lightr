//! Large-tree metadata path must retain input selection, bytes, modes and links.
use super::*;
use std::fs;
use std::os::unix::fs::{symlink, PermissionsExt};
use tempfile::TempDir;

#[test]
fn large_scan_preserves_warm_mutation_and_racy_manifest_semantics() {
    let _guard = crate::TEST_ENV_LOCK.lock().unwrap();
    let temporary = TempDir::new().unwrap();
    struct RestoreHome(Option<std::ffi::OsString>);
    impl Drop for RestoreHome {
        fn drop(&mut self) {
            match &self.0 {
                Some(value) => std::env::set_var("LIGHTR_HOME", value),
                None => std::env::remove_var("LIGHTR_HOME"),
            }
        }
    }
    let _restore = RestoreHome(std::env::var_os("LIGHTR_HOME"));
    std::env::set_var("LIGHTR_HOME", temporary.path().join("home"));
    let root = temporary.path().join("source");
    fs::create_dir_all(root.join(".git")).unwrap();
    fs::create_dir(root.join("empty")).unwrap();
    fs::write(root.join(".gitignore"), "ignored\n").unwrap();
    fs::write(root.join(".lightrignore"), "custom-ignored\n").unwrap();
    for name in ["ignored", "custom-ignored", ".git/hidden"] {
        fs::write(root.join(name), b"must not be captured").unwrap();
    }
    for i in 0..2100 {
        fs::write(root.join(format!("file-{i:04}")), i.to_string()).unwrap();
    }
    symlink("file-0000", root.join("link")).unwrap();
    let mut index = Index::empty();
    let cold = scan(&root, &mut index).unwrap();
    assert_eq!(cold.rehashed, 2102);
    assert_eq!(cold.manifest.entries.len(), 2104);
    for entry in &cold.manifest.entries {
        if let Entry::File { path, digest, .. } = entry {
            assert_eq!(
                *digest,
                Digest::of_bytes(&fs::read(root.join(path)).unwrap())
            );
        }
    }
    // Deterministic cache-age control, avoiding sleeps/mtime-resolution guesses.
    index.saved_at_ns = u64::MAX;
    let warm = scan(&root, &mut index).unwrap();
    assert_eq!(warm.from_index, 2102);
    assert_eq!(warm.rehashed, 0);
    assert_eq!(cold.manifest.encode(), warm.manifest.encode());
    fs::write(root.join("file-0000"), b"changed-length").unwrap();
    fs::set_permissions(root.join("file-0001"), fs::Permissions::from_mode(0o755)).unwrap();
    fs::remove_file(root.join("file-0002")).unwrap();
    fs::remove_file(root.join("link")).unwrap();
    symlink("missing\\literal", root.join("link")).unwrap();
    let changed = scan(&root, &mut index).unwrap();
    assert_ne!(changed.manifest.digest(), warm.manifest.digest());
    assert!(!changed
        .manifest
        .entries
        .iter()
        .any(|entry| entry.path() == "file-0002"));
    assert!(changed.manifest.entries.iter().any(|entry| matches!(entry,
        Entry::File { path, mode: 0o755, .. } if path == "file-0001")));
    assert!(changed.manifest.entries.iter().any(|entry| matches!(entry,
        Entry::Symlink { path, target } if path == "link" && target == "missing\\literal")));
    // No cached stat can pass an index save-time of zero: every selected file
    // must be rehashed, even if size/mtime/inode otherwise still match.
    index.saved_at_ns = 0;
    let racy = scan(&root, &mut index).unwrap();
    assert_eq!(racy.from_index, 0);
    assert_eq!(racy.rehashed, 2101);
    assert_eq!(racy.manifest.encode(), changed.manifest.encode());
}
