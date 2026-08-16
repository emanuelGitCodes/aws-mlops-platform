import { useState } from "react";

import { predict } from "../api";
import { ApiError } from "../types";
import type { CustomerRecord, ModelSchema, NumericBound, Prediction } from "../types";

/**
 * Build the starting record.
 *
 * The backend publishes the canonical sample payloads, so the form opens on a
 * real customer. Without them it falls back to the schema's own defaults, which
 * describe a customer who has never paid anything.
 */
function initialRecord(schema: ModelSchema): CustomerRecord {
  const example = schema.examples?.[0];
  if (example) return { ...example.record };

  const record: CustomerRecord = {};
  for (const column of schema.feature_columns) {
    const options = schema.categorical_values[column];
    record[column] = options ? (options[0] ?? "") : 0;
  }
  return record;
}

/** Read a numeric column's range. An absent bound leaves the input open. */
function boundOf(schema: ModelSchema, column: string): NumericBound {
  return schema.numeric_bounds?.[column] ?? { integer: false };
}

/**
 * A column the model treats as an integer flag renders as a choice.
 *
 * The bound comes from the shared request model, so a 0-or-1 column is
 * recognised from its own contract rather than from its name.
 */
function isFlag(bound: NumericBound): boolean {
  return bound.integer && bound.minimum === 0 && bound.maximum === 1;
}

export function PredictForm({ schema }: { schema: ModelSchema }) {
  const [record, setRecord] = useState<CustomerRecord>(() => initialRecord(schema));
  const [activeExample, setActiveExample] = useState<string | null>(
    schema.examples?.[0]?.key ?? null,
  );
  const [result, setResult] = useState<Prediction | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);

  const examples = schema.examples ?? [];

  function update(column: string, value: string | number) {
    setRecord((previous) => ({ ...previous, [column]: value }));
    // The record no longer matches the example it started from.
    setActiveExample(null);
  }

  function loadExample(key: string) {
    const example = examples.find((candidate) => candidate.key === key);
    if (!example) return;
    setRecord({ ...example.record });
    setActiveExample(key);
    setResult(null);
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setResult(null);
    try {
      setResult(await predict(record));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause : new ApiError("the prediction failed", 0));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="prediction-console">
      <div className="console-bar">
        <span className="console-route">POST /api/predict</span>
        {examples.length > 0 && (
          <div className="console-presets">
            <span id="preset-label">Load</span>
            <div role="group" aria-labelledby="preset-label">
              {examples.map((example) => (
                <button
                  className={`preset-key${activeExample === example.key ? " is-active" : ""}`}
                  type="button"
                  key={example.key}
                  aria-pressed={activeExample === example.key}
                  onClick={() => loadExample(example.key)}
                >
                  {example.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <form onSubmit={submit}>
        <div className="input-grid">
          {schema.feature_columns.map((column) => {
            const options = schema.categorical_values[column];
            const bound = boundOf(schema, column);
            const flag = !options && isFlag(bound);
            return (
              <label key={column}>
                <span>{column}</span>
                {options ? (
                  <select
                    value={String(record[column] ?? "")}
                    onChange={(event) => update(column, event.target.value)}
                  >
                    {options.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : flag ? (
                  <select
                    value={String(record[column] ?? 0)}
                    onChange={(event) => update(column, Number(event.target.value))}
                  >
                    <option value="0">No</option>
                    <option value="1">Yes</option>
                  </select>
                ) : (
                  <input
                    type="number"
                    step={bound.integer ? "1" : "any"}
                    min={bound.minimum}
                    max={bound.maximum}
                    value={String(record[column] ?? "")}
                    onChange={(event) => update(column, Number(event.target.value))}
                  />
                )}
              </label>
            );
          })}
        </div>

        <div className="console-actions">
          <p className="console-note">
            The request is validated against the same schema the pipeline uses, then signed
            with the server's own role. Your browser never holds AWS credentials.
          </p>
          <button className="submit-command" type="submit" disabled={pending}>
            {pending ? "Scoring…" : "Run prediction"}
          </button>
        </div>
      </form>

      {error && <PredictionFault error={error} />}

      {result && (
        <div className="inline-result" aria-live="polite">
          <span>Result</span>
          <strong>{result.churn ? "Likely to churn" : "Likely to stay"}</strong>
          <p>
            Probability {result.churn_probability.toFixed(4)}, against a{" "}
            {schema.decision_threshold} decision threshold.
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * Explain a failed prediction.
 *
 * A 502 means the inference endpoint is not answering. That is the ordinary
 * state of this platform between demonstrations: a SageMaker endpoint costs
 * money for every hour it runs, so it does not stay up to serve a portfolio
 * page. The reader gets that fact rather than a bare failure.
 */
function PredictionFault({ error }: { error: ApiError }) {
  const dormant = error.status === 502;
  return (
    <div className={`inline-result ${dormant ? "is-dormant" : "is-error"}`} role="alert">
      <span>{dormant ? "Endpoint idle" : "Request failed"}</span>
      <strong>{dormant ? "The inference endpoint is not running" : error.message}</strong>
      <p>
        {dormant
          ? "A SageMaker endpoint bills for every hour it stays up, so this one is " +
            "started for a demonstration and stopped afterwards. The rest of the " +
            "platform on this page is unaffected."
          : "Check the values, then try again."}
      </p>
    </div>
  );
}
