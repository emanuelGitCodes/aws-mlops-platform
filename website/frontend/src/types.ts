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

/** One numeric column's range, read from the shared request model. */
export interface NumericBound {
  integer: boolean;
  minimum?: number;
  maximum?: number;
}

/** One canonical request payload the backend publishes to seed the form. */
export interface SchemaExample {
  key: string;
  label: string;
  record: CustomerRecord;
}

export interface ModelSchema {
  feature_columns: string[];
  label_column: string;
  numeric_columns: string[];
  categorical_values: Record<string, string[]>;
  numeric_bounds?: Record<string, NumericBound>;
  decision_threshold: number;
  examples?: SchemaExample[];
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
