use revenue_growth_core::{journal, GuestInput};
use risc0_zkvm::guest::env;

fn main() {
    let input: GuestInput = env::read();
    let public_journal = journal(&input.proof_input, input.image_id)
        .expect("the committed revenue growth input must be canonical and internally consistent");
    env::commit(&public_journal);
}
