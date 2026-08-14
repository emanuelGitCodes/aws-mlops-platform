---
type: decision
title: Dataset provenance and the untracked CSV
created: "2026-08-14"
updated: "2026-08-14"
sources: ["../../../README.md", "../../../.gitignore", "../../../src/pipeline/preprocess.py", "https://www.kaggle.com/datasets/blastchar/telco-customer-churn", "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv"]
summary: "The Telco churn CSV stays untracked and is pinned by SHA-256 to the public IBM/Kaggle file, because the seeded split makes every downstream metric depend on the exact row order."
---
# Dataset provenance and the untracked CSV

## Confirmed

The training data is the IBM Telco Customer Churn dataset. Kaggle publishes
it as `blastchar/telco-customer-churn`, file
`WA_Fn-UseC_-Telco-Customer-Churn.csv`, 7,043 data rows plus a header. IBM
hosts a byte-identical mirror that needs no login:
`https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv`.

The repository does not track the file. `.gitignore` excludes `telco/`, and
the local working copy lives at `telco/telco.csv`.

Two hashes identify the file:

| Variant | SHA-256 |
|---|---|
| Canonical LF bytes (Kaggle, IBM mirror) | `16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91` |
| CRLF line endings (the reference working copy) | `88be4b93fbe0cc83421af1c503794c97c342eca914c1576db7c276e61d61358a` |

A 2026-08-14 check confirmed the identity: `tr -d '\r'` over the reference
working copy produced the canonical hash, and two independent public mirrors
(IBM's repository and a third-party GitHub copy) both served the canonical
bytes. The two variants hold the same rows in the same order.

`split_records` in `src/pipeline/preprocess.py` shuffles the input rows with
`random.Random(42)` and cuts 70/15/15 train, validation, and held-out test
splits by position. The splits, the evaluation report, and the reported AUC
are therefore deterministic only for one exact row order.

## Synthesis

The decision has two parts:

- **The CSV stays untracked.** The Kaggle listing carries no clear
  redistribution license ("Data files © Original Authors"), and this
  repository grants no license of its own. Pointing at IBM's public mirror
  avoids redistributing a file this repository does not own.
- **The hash is the contract.** A reader who fetches the mirror and matches
  the canonical SHA-256 holds the same rows in the same order as the
  reference account. That makes the pipeline's splits, and the first
  champion's metrics, reproducible from a clean checkout.

Anyone who reproduces the platform MUST verify the fetched file against one
of the two hashes before the first upload. A file with any other hash
produces different splits and a different AUC, and no later step detects the
substitution.

## Tensions or open questions

- The IBM mirror is a file inside a third-party repository, not a versioned
  dataset release. If IBM moves or edits the file, the README fetch command
  breaks or, worse, fetches different bytes. The hash check is the guard:
  a mismatch stops the reader before any AWS state depends on the file.
- No recorded reference AUC exists yet for a from-scratch run. The hash pins
  the input; a wiki record of the expected first-champion AUC would pin the
  output. Write one when the scratch-account rebuild test runs.

## Related pages

- [Platform design decisions](platform-design.md)
- [Validation versus preprocessing contracts](../concepts/contracts-and-preprocessing.md)
- [Complete teardown and rebuild](../architecture/teardown-and-rebuild.md)
