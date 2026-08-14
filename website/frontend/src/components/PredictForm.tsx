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
    <section>
      <h2>Try the model</h2>
      <form onSubmit={submit}>
        <div className="grid">
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
        <button type="submit" disabled={pending}>
          {pending ? "Scoring…" : "Predict"}
        </button>
      </form>

      {error && <p role="alert">{error}</p>}
      {result && (
        <p>
          <strong>{result.churn ? "Likely to churn" : "Likely to stay"}</strong> — probability{" "}
          {result.churn_probability.toFixed(4)} against a {schema.decision_threshold} threshold.
        </p>
      )}
    </section>
  );
}
