// The shapes the backend returns.
//
// `ModelSchema` describes the model contract, and the form is built from it at
// run time. The field names and the allowed values are NOT restated here:
// `src/common/features.py` owns them, `/api/schema` publishes them, and
// `PredictForm` renders whatever arrives. A new feature column needs no
// frontend change.
//
// These types can be generated from `/api/openapi.json` when the API grows
// past hand-written types.

export interface ModelSchema {
  feature_columns: string[];
  label_column: string;
  numeric_columns: string[];
  categorical_values: Record<string, string[]>;
  decision_threshold: number;
}

export interface EvaluationReport {
  available: boolean;
  key?: string;
  generated_at?: string;
  report?: unknown;
  error?: string;
}

export interface Prediction {
  churn_probability: number;
  churn: boolean;
}

export interface Subscription {
  subscribed: boolean;
  created_at: string;
}

/** One record sent to `/api/predict`. Values are strings or numbers. */
export type CustomerRecord = Record<string, string | number>;

/** An error the API reported, with the status it used. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
