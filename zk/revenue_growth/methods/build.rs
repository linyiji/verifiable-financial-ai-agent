use std::{collections::HashMap, path::PathBuf};

use risc0_build::{DockerOptionsBuilder, GuestOptionsBuilder};

const RISC0_GUEST_BUILDER_TAG: &str =
    "r0.1.88.0@sha256:3e12f71bacd27527a61dea96fa0e53e468c99aa261d3a1019b593f6dbd943eb3";

fn main() {
    if let Ok(configured_tag) = std::env::var("RISC0_DOCKER_CONTAINER_TAG") {
        assert_eq!(
            configured_tag, RISC0_GUEST_BUILDER_TAG,
            "RISC0_DOCKER_CONTAINER_TAG must match the repository pin"
        );
    }
    assert!(
        std::env::var_os("RISC0_SKIP_BUILD").is_none(),
        "RISC0_SKIP_BUILD is forbidden for a formal proof build"
    );

    let methods_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let workspace_root = methods_dir
        .parent()
        .expect("methods crate must be inside the proof workspace");
    let docker_options = DockerOptionsBuilder::default()
        .root_dir(workspace_root)
        .docker_container_tag(RISC0_GUEST_BUILDER_TAG)
        .build()
        .expect("valid deterministic Docker options");
    let guest_options = GuestOptionsBuilder::default()
        .use_docker(docker_options)
        .build()
        .expect("valid deterministic guest options");

    risc0_build::embed_methods_with_options(HashMap::from([(
        "revenue-growth-guest",
        guest_options,
    )]));
}
