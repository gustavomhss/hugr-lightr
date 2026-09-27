//! Internal submodules of lightr-store.
//!
//! All items re-exported from here are re-exported again at the crate root
//! in `lib.rs`, preserving the frozen public API.

pub mod ac;
pub mod cas;
pub mod cow;
pub mod image_ref;
pub mod imgmeta;
pub mod lock;
pub mod refs;
pub mod usage;
pub mod volume;

/// Additive SI-01 wire/error primitives; existing Store routing is unchanged.
pub mod foundation;
