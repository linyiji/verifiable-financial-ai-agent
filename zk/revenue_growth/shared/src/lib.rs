use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};
use std::collections::BTreeSet;

pub const INPUT_SCHEMA_VERSION: &str = "risc0_revenue_growth_input_v1";
pub const JOURNAL_SCHEMA_VERSION: &str = "risc0_revenue_growth_journal_v1";
pub const FORMULA_ID: &str = "revenue_growth_v1";
pub const CAPABILITY_ID: &str = "revenue_growth";

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CanonicalInputs {
    pub prior_revenue_minor: i64,
    pub current_revenue_minor: i64,
    pub currency: String,
    pub scale: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProofInput {
    pub schema_version: String,
    pub run_id: String,
    pub calculation_id: String,
    pub formula_id: String,
    pub capability_id: String,
    pub implementation_hash: String,
    pub input_evidence_refs: Vec<String>,
    pub canonical_inputs: CanonicalInputs,
    pub input_commitment: String,
    pub expected_output_commitment: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GuestInput {
    pub proof_input: ProofInput,
    pub image_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CanonicalResult {
    pub growth_numerator: i128,
    pub growth_denominator: i128,
    pub unit: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Journal {
    pub schema_version: String,
    pub formula_id: String,
    pub image_id: String,
    pub input_commitment: String,
    pub expected_output_commitment: String,
    pub canonical_result: CanonicalResult,
}

fn write_field(hasher: &mut Sha256, name: &str, value: &[u8]) {
    hasher.update((name.len() as u32).to_be_bytes());
    hasher.update(name.as_bytes());
    hasher.update((value.len() as u64).to_be_bytes());
    hasher.update(value);
}

fn finish_hash(hasher: Sha256) -> String {
    let digest = hasher.finalize();
    let mut encoded = String::with_capacity(71);
    encoded.push_str("sha256:");
    for byte in digest {
        use std::fmt::Write as _;
        write!(&mut encoded, "{byte:02x}").expect("writing to String cannot fail");
    }
    encoded
}

pub fn output_commitment(formula_id: &str, result: &CanonicalResult) -> String {
    let mut hasher = Sha256::new();
    write_field(
        &mut hasher,
        "domain",
        b"verifiable-financial-agent/revenue-growth-output/v1",
    );
    write_field(&mut hasher, "formula_id", formula_id.as_bytes());
    write_field(
        &mut hasher,
        "growth_numerator",
        result.growth_numerator.to_string().as_bytes(),
    );
    write_field(
        &mut hasher,
        "growth_denominator",
        result.growth_denominator.to_string().as_bytes(),
    );
    write_field(&mut hasher, "unit", result.unit.as_bytes());
    finish_hash(hasher)
}

pub fn input_commitment(input: &ProofInput) -> String {
    let mut hasher = Sha256::new();
    write_field(
        &mut hasher,
        "domain",
        b"verifiable-financial-agent/revenue-growth-input/v1",
    );
    write_field(
        &mut hasher,
        "schema_version",
        input.schema_version.as_bytes(),
    );
    write_field(&mut hasher, "run_id", input.run_id.as_bytes());
    write_field(
        &mut hasher,
        "calculation_id",
        input.calculation_id.as_bytes(),
    );
    write_field(&mut hasher, "formula_id", input.formula_id.as_bytes());
    write_field(&mut hasher, "capability_id", input.capability_id.as_bytes());
    write_field(
        &mut hasher,
        "implementation_hash",
        input.implementation_hash.as_bytes(),
    );
    write_field(
        &mut hasher,
        "input_evidence_ref_count",
        input.input_evidence_refs.len().to_string().as_bytes(),
    );
    for evidence_ref in &input.input_evidence_refs {
        write_field(&mut hasher, "input_evidence_ref", evidence_ref.as_bytes());
    }
    write_field(
        &mut hasher,
        "prior_revenue_minor",
        input
            .canonical_inputs
            .prior_revenue_minor
            .to_string()
            .as_bytes(),
    );
    write_field(
        &mut hasher,
        "current_revenue_minor",
        input
            .canonical_inputs
            .current_revenue_minor
            .to_string()
            .as_bytes(),
    );
    write_field(
        &mut hasher,
        "currency",
        input.canonical_inputs.currency.as_bytes(),
    );
    write_field(
        &mut hasher,
        "scale",
        input.canonical_inputs.scale.to_string().as_bytes(),
    );
    write_field(
        &mut hasher,
        "expected_output_commitment",
        input.expected_output_commitment.as_bytes(),
    );
    finish_hash(hasher)
}

fn gcd(mut left: i128, mut right: i128) -> i128 {
    left = left.abs();
    right = right.abs();
    while right != 0 {
        let remainder = left % right;
        left = right;
        right = remainder;
    }
    left
}

pub fn calculate(inputs: &CanonicalInputs) -> Result<CanonicalResult, String> {
    if inputs.prior_revenue_minor == 0 {
        return Err("prior revenue must not be zero".to_owned());
    }
    if inputs.scale > 18 {
        return Err("scale must be at most 18".to_owned());
    }
    if inputs.currency.is_empty()
        || inputs.currency.len() > 16
        || !inputs
            .currency
            .bytes()
            .all(|byte| byte.is_ascii_uppercase())
    {
        return Err("currency must be 1-16 uppercase ASCII characters".to_owned());
    }

    let prior = i128::from(inputs.prior_revenue_minor);
    let current = i128::from(inputs.current_revenue_minor);
    let numerator = current - prior;
    let denominator = prior.abs();
    let divisor = gcd(numerator, denominator);

    Ok(CanonicalResult {
        growth_numerator: numerator / divisor,
        growth_denominator: denominator / divisor,
        unit: "ratio".to_owned(),
    })
}

pub fn validate_and_calculate(input: &ProofInput) -> Result<CanonicalResult, String> {
    if input.schema_version != INPUT_SCHEMA_VERSION {
        return Err("unsupported input schema version".to_owned());
    }
    if input.formula_id != FORMULA_ID {
        return Err("unsupported formula id".to_owned());
    }
    if input.capability_id != CAPABILITY_ID {
        return Err("unsupported capability id".to_owned());
    }
    if input.run_id.is_empty()
        || input.calculation_id.is_empty()
        || input.implementation_hash.is_empty()
    {
        return Err("run, calculation, and implementation bindings are required".to_owned());
    }
    if input.input_evidence_refs.len() != 2
        || input.input_evidence_refs.iter().any(String::is_empty)
        || input
            .input_evidence_refs
            .iter()
            .collect::<BTreeSet<_>>()
            .len()
            != input.input_evidence_refs.len()
    {
        return Err("exactly two distinct evidence references are required".to_owned());
    }

    let result = calculate(&input.canonical_inputs)?;
    if output_commitment(&input.formula_id, &result) != input.expected_output_commitment {
        return Err("expected output commitment mismatch".to_owned());
    }
    if input_commitment(input) != input.input_commitment {
        return Err("input commitment mismatch".to_owned());
    }
    Ok(result)
}

pub fn journal(input: &ProofInput, image_id: String) -> Result<Journal, String> {
    let canonical_result = validate_and_calculate(input)?;
    Ok(Journal {
        schema_version: JOURNAL_SCHEMA_VERSION.to_owned(),
        formula_id: input.formula_id.clone(),
        image_id,
        input_commitment: input.input_commitment.clone(),
        expected_output_commitment: input.expected_output_commitment.clone(),
        canonical_result,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn revenue_growth_is_an_exact_reduced_rational() {
        let output = calculate(&CanonicalInputs {
            prior_revenue_minor: 100,
            current_revenue_minor: 125,
            currency: "USD".to_owned(),
            scale: 0,
        })
        .unwrap();
        assert_eq!(output.growth_numerator, 1);
        assert_eq!(output.growth_denominator, 4);
    }

    #[test]
    fn negative_growth_keeps_sign_on_numerator() {
        let output = calculate(&CanonicalInputs {
            prior_revenue_minor: 100,
            current_revenue_minor: 80,
            currency: "USD".to_owned(),
            scale: 0,
        })
        .unwrap();
        assert_eq!(output.growth_numerator, -1);
        assert_eq!(output.growth_denominator, 5);
    }

    #[test]
    fn commitments_match_the_cross_language_fixture() {
        let mut input = ProofInput {
            schema_version: INPUT_SCHEMA_VERSION.to_owned(),
            run_id: "RUN-RISC0-NVDA-001".to_owned(),
            calculation_id: "CALC-REVENUE-GROWTH-001".to_owned(),
            formula_id: FORMULA_ID.to_owned(),
            capability_id: CAPABILITY_ID.to_owned(),
            implementation_hash:
                "sha256:f583ff894c388b8677bde486760ea14fc702278cfaa2229cb007221f1ba20765".to_owned(),
            input_evidence_refs: vec![
                "EVD-NVDA-REVENUE-FY2024".to_owned(),
                "EVD-NVDA-REVENUE-FY2025".to_owned(),
            ],
            canonical_inputs: CanonicalInputs {
                prior_revenue_minor: 6_092_200_000_000,
                current_revenue_minor: 13_049_700_000_000,
                currency: "USD".to_owned(),
                scale: 2,
            },
            input_commitment: String::new(),
            expected_output_commitment: String::new(),
        };
        let result = calculate(&input.canonical_inputs).unwrap();
        input.expected_output_commitment = output_commitment(FORMULA_ID, &result);
        input.input_commitment = input_commitment(&input);

        assert_eq!(
            input.expected_output_commitment,
            "sha256:a701eaf10065178b019ff90f3ea20a82f43500afe36f6bfb7a71bff117506d20"
        );
        assert_eq!(
            input.input_commitment,
            "sha256:515bde26968e1b25e621866342adf4f9438b0a45c6ce3e01126509ebc127d640"
        );
        assert_eq!(validate_and_calculate(&input).unwrap(), result);
    }
}
