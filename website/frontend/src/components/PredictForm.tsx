import { useState } from "react";

import { predict } from "../api";
import { ApiError } from "../types";
import type { CustomerRecord, ModelSchema, Prediction } from "../types";

/** Build the starting record from the schema the backend published. */
function initialRecord(schema: ModelSchema): CustomerRecord {
  const record: CustomerRecord = {};
  for (const column of schema.feature_columns) {
    const options = schema.categorical_values[column];
    record[column] = options ? (options[0] ?? "") : 0;
  }
  return record;
}

export function PredictForm({ schema }: { schema: ModelSchema }) {
  const [record, setRecord] = useState<CustomerRecord>(() => initialRecord(schema));
  const [result, setResult] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const numeric = new Set(schema.numeric_columns);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setResult(null);
    try {
      setResult(await predict(record));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "the prediction failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="prediction-console">
      <div className="console-bar">
        <span>POST /api/predict</span>
        <span>Schema-driven request</span>
      </div>
      <form onSubmit={submit}>
        <div className="input-grid">
          {schema.feature_columns.map((column) => {
            const options = schema.categorical_values[column];
            return (
              <label key={column}>
                <span>{column}</span>
                {options ? (
                  <select
                    value={String(record[column] ?? "")}
                    onChange={(event) =>
                      setRecord({ ...record, [column]: event.target.value })
                    }
                  >
                    {options.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    step={numeric.has(column) ? "any" : "1"}
                    value={String(record[column] ?? "")}
                    onChange={(event) =>
                      setRecord({ ...record, [column]: Number(event.target.value) })
                    }
                  />
                )}
              </label>
            );
          })}
        </div>
        <button className="submit-command" type="submit" disabled={pending}>
          {pending ? "Scoring record…" : "Run prediction"}
        </button>
      </form>

      {error && <p className="inline-result is-error" role="alert">{error}. Check the values, then try again.</p>}
      {result && (
        <div className="inline-result" aria-live="polite">
          <span>Prediction result</span>
          <strong>{result.churn ? "Likely to churn" : "Likely to stay"}</strong>
          <p>
            Probability {result.churn_probability.toFixed(4)} against a{" "}
            {schema.decision_threshold} decision threshold.
          </p>
        </div>
      )}
    </div>
  );
}
