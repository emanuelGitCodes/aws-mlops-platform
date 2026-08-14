import { useEffect, useState } from "react";

import { getResults, getSchema } from "./api";
import { LatestEvaluation } from "./components/LatestEvaluation";
import { PredictForm } from "./components/PredictForm";
import { SchemaTable } from "./components/SchemaTable";
import { SubscribeForm } from "./components/SubscribeForm";
import { ApiError } from "./types";
import type { EvaluationReport, ModelSchema } from "./types";

export function App() {
  const [schema, setSchema] = useState<ModelSchema | null>(null);
  const [results, setResults] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The schema drives every other section, so a failure here is fatal to the
    // page. A failed report is not: that section reports its own state.
    getSchema()
      .then(setSchema)
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : "the model schema is unavailable"),
      );
    getResults()
      .then(setResults)
      .catch(() => setResults({ available: false, error: "the report is unavailable" }));
  }, []);

  return (
    <main>
      <h1>Telco churn model</h1>
      <p>An MLOps reference platform on AWS. This page reads the live model.</p>

      {error && <p role="alert">{error}</p>}
      {!schema && !error && <p>Loading the model contract…</p>}

      {schema && (
        <>
          <SchemaTable schema={schema} />
          {results && <LatestEvaluation results={results} schema={schema} />}
          <PredictForm schema={schema} />
        </>
      )}
      <SubscribeForm />
    </main>
  );
}
