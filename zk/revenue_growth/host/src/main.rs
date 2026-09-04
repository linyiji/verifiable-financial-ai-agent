use anyhow::{anyhow, bail, Context, Result};
use hex::FromHex;
use revenue_growth_core::{journal, validate_and_calculate, GuestInput, Journal, ProofInput};
use revenue_growth_methods::{REVENUE_GROWTH_GUEST_ELF, REVENUE_GROWTH_GUEST_ID};
use risc0_zkvm::{default_prover, sha::Digest, ExecutorEnv, Receipt};
use serde::Serialize;
use sha2::{Digest as _, Sha256};
use std::{env, fs, path::PathBuf, time::Instant};

#[derive(Serialize)]
struct CommandOutput {
    status: &'static str,
    backend: &'static str,
    program_id: &'static str,
    image_id: String,
    receipt_path: Option<String>,
    receipt_hash: Option<String>,
    journal_hash: Option<String>,
    input_commitment: Option<String>,
    expected_output_commitment: Option<String>,
    canonical_result: Option<revenue_growth_core::CanonicalResult>,
    proving_duration_ms: Option<u128>,
    dev_mode: bool,
}

enum Command {
    ImageId,
    Prove {
        input: PathBuf,
        receipt: PathBuf,
    },
    Verify {
        input: PathBuf,
        receipt: PathBuf,
        expected_image_id: Option<String>,
    },
}

fn parse_args() -> Result<Command> {
    let mut args = env::args().skip(1);
    let command = args
        .next()
        .context("expected command: image-id, prove, or verify")?;
    if command == "image-id" {
        if args.next().is_some() {
            bail!("image-id takes no arguments");
        }
        return Ok(Command::ImageId);
    }

    let mut input = None;
    let mut receipt = None;
    let mut expected_image_id = None;
    while let Some(flag) = args.next() {
        let value = args
            .next()
            .with_context(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--input" => input = Some(PathBuf::from(value)),
            "--receipt" => receipt = Some(PathBuf::from(value)),
            "--expected-image-id" => expected_image_id = Some(value),
            _ => bail!("unknown argument: {flag}"),
        }
    }
    let input = input.context("--input is required")?;
    let receipt = receipt.context("--receipt is required")?;
    match command.as_str() {
        "prove" => {
            if expected_image_id.is_some() {
                bail!("--expected-image-id is only valid for verify");
            }
            Ok(Command::Prove { input, receipt })
        }
        "verify" => Ok(Command::Verify {
            input,
            receipt,
            expected_image_id,
        }),
        _ => bail!("unknown command: {command}"),
    }
}

fn reject_dev_mode() -> Result<()> {
    if env::var_os("RISC0_DEV_MODE").is_some() {
        bail!("RISC0_DEV_MODE is forbidden for this proof host");
    }
    Ok(())
}

fn image_id() -> String {
    Digest::from(REVENUE_GROWTH_GUEST_ID).to_string()
}

fn read_input(path: &PathBuf) -> Result<ProofInput> {
    let encoded = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    let input = serde_json::from_slice::<ProofInput>(&encoded)
        .with_context(|| format!("invalid proof input {}", path.display()))?;
    validate_and_calculate(&input)
        .map_err(|error| anyhow!("proof input validation failed: {error}"))?;
    Ok(input)
}

fn sha256_prefixed(encoded: &[u8]) -> String {
    let mut output = String::with_capacity(71);
    output.push_str("sha256:");
    for byte in Sha256::digest(encoded) {
        use std::fmt::Write as _;
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
    }
    output
}

fn prove(input_path: PathBuf, receipt_path: PathBuf) -> Result<CommandOutput> {
    reject_dev_mode()?;
    let input = read_input(&input_path)?;
    let expected_journal = journal(&input, image_id())
        .map_err(|error| anyhow!("failed to derive journal: {error}"))?;
    let env = ExecutorEnv::builder()
        .write(&GuestInput {
            proof_input: input.clone(),
            image_id: image_id(),
        })
        .context("failed to encode guest input")?
        .build()
        .context("failed to build executor environment")?;

    let started = Instant::now();
    let prove_info = default_prover()
        .prove(env, REVENUE_GROWTH_GUEST_ELF)
        .context("RISC Zero proving failed")?;
    let duration = started.elapsed().as_millis();
    let receipt = prove_info.receipt;
    let actual_journal: Journal = receipt
        .journal
        .decode()
        .context("failed to decode generated journal")?;
    if actual_journal != expected_journal {
        bail!("generated journal does not match canonical host expectation");
    }

    let encoded = bincode::serialize(&receipt).context("failed to serialize receipt")?;
    if let Some(parent) = receipt_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    fs::write(&receipt_path, &encoded)
        .with_context(|| format!("failed to write {}", receipt_path.display()))?;

    Ok(CommandOutput {
        status: "GENERATED",
        backend: "risc0",
        program_id: "revenue_growth_v1",
        image_id: image_id(),
        receipt_path: Some(receipt_path.display().to_string()),
        receipt_hash: Some(sha256_prefixed(&encoded)),
        journal_hash: Some(sha256_prefixed(&receipt.journal.bytes)),
        input_commitment: Some(input.input_commitment),
        expected_output_commitment: Some(input.expected_output_commitment),
        canonical_result: Some(actual_journal.canonical_result),
        proving_duration_ms: Some(duration),
        dev_mode: false,
    })
}

fn verify(
    input_path: PathBuf,
    receipt_path: PathBuf,
    expected_image_id: Option<String>,
) -> Result<CommandOutput> {
    reject_dev_mode()?;
    let encoded = fs::read(&receipt_path)
        .with_context(|| format!("failed to read {}", receipt_path.display()))?;
    let receipt: Receipt = bincode::deserialize(&encoded).context("invalid receipt encoding")?;

    // The normal path pins the compiled image; an explicit override exists for negative tests.
    let compiled_image_id = image_id();
    let verification_image_id = match expected_image_id {
        Some(expected) => Digest::from_hex(expected).context("invalid expected image id")?,
        None => Digest::from(REVENUE_GROWTH_GUEST_ID),
    };
    receipt
        .verify(verification_image_id)
        .context("receipt cryptographic verification failed")?;

    let input = read_input(&input_path)?;
    let expected_journal = journal(&input, compiled_image_id.clone())
        .map_err(|error| anyhow!("failed to derive expected journal: {error}"))?;
    let actual_journal: Journal = receipt
        .journal
        .decode()
        .context("failed to decode verified journal")?;
    if actual_journal != expected_journal {
        bail!("verified journal does not match supplied canonical expectation");
    }

    Ok(CommandOutput {
        status: "VERIFIED",
        backend: "risc0",
        program_id: "revenue_growth_v1",
        image_id: compiled_image_id,
        receipt_path: Some(receipt_path.display().to_string()),
        receipt_hash: Some(sha256_prefixed(&encoded)),
        journal_hash: Some(sha256_prefixed(&receipt.journal.bytes)),
        input_commitment: Some(input.input_commitment),
        expected_output_commitment: Some(input.expected_output_commitment),
        canonical_result: Some(actual_journal.canonical_result),
        proving_duration_ms: None,
        dev_mode: false,
    })
}

fn run() -> Result<CommandOutput> {
    match parse_args()? {
        Command::ImageId => Ok(CommandOutput {
            status: "READY",
            backend: "risc0",
            program_id: "revenue_growth_v1",
            image_id: image_id(),
            receipt_path: None,
            receipt_hash: None,
            journal_hash: None,
            input_commitment: None,
            expected_output_commitment: None,
            canonical_result: None,
            proving_duration_ms: None,
            dev_mode: false,
        }),
        Command::Prove { input, receipt } => prove(input, receipt),
        Command::Verify {
            input,
            receipt,
            expected_image_id,
        } => verify(input, receipt, expected_image_id),
    }
}

fn main() {
    match run() {
        Ok(output) => println!("{}", serde_json::to_string(&output).unwrap()),
        Err(error) => {
            eprintln!("{error:#}");
            std::process::exit(1);
        }
    }
}
