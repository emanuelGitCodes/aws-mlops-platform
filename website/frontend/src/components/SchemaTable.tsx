import type { ModelSchema } from "../types";

export function SchemaTable({ schema }: { schema: ModelSchema }) {
  const numeric = new Set(schema.numeric_columns);
  const categorical = schema.feature_columns.filter((column) => !numeric.has(column));

  return (
    <section className="evidence-panel schema-panel">
      <h3>Input contract</h3>
      <p>
        One module owns the feature order and the accepted values. Training, ingestion,
        the inference proxy, and this form all read it, so none of them can drift.
        The table below is served by the API, not written into the page.
      </p>

      <dl className="schema-counts">
        <div>
          <dt>Features</dt>
          <dd>{schema.feature_columns.length}</dd>
        </div>
        <div>
          <dt>Categorical</dt>
          <dd>{categorical.length}</dd>
        </div>
        <div>
          <dt>Numeric</dt>
          <dd>{schema.numeric_columns.length}</dd>
        </div>
        <div>
          <dt>Label</dt>
          <dd>
            <code>{schema.label_column}</code>
          </dd>
        </div>
      </dl>

      <div className="table-scroll">
        <table>
          <caption className="sr-only">
            Every feature column, its type, and the values it accepts
          </caption>
          <thead>
            <tr>
              <th scope="col">Column</th>
              <th scope="col">Type</th>
              <th scope="col">Accepted values</th>
            </tr>
          </thead>
          <tbody>
            {schema.feature_columns.map((column) => (
              <tr key={column}>
                <th scope="row">
                  <code>{column}</code>
                </th>
                <td>{numeric.has(column) ? "number" : "category"}</td>
                <td>{schema.categorical_values[column]?.join(", ") ?? boundText(schema, column)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Describe a numeric column's accepted range from its published bound. */
function boundText(schema: ModelSchema, column: string): string {
  const bound = schema.numeric_bounds?.[column];
  if (!bound) return "any number";
  const kind = bound.integer ? "integer" : "decimal";
  if (bound.minimum !== undefined && bound.maximum !== undefined) {
    return `${kind} ${bound.minimum} to ${bound.maximum}`;
  }
  if (bound.minimum !== undefined) return `${kind} from ${bound.minimum}`;
  return `any ${kind}`;
}
