# Model artifacts

`l3_correction.joblib` is supplied at deployment time and is intentionally not
committed. It must contain an `east_model` and a `north_model`, each exposing a
scikit-learn-compatible `predict()` method.

`model_metadata.json` must contain the exact runtime feature list and the
number of training records. See `docs/model-engine-implementation-spec.md`.
