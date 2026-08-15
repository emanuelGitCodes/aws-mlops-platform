import type { ModelSchema } from "../types";

export function SchemaTable({ schema }: { schema: ModelSchema }) {
  const numeric = new Set(schema.numeric_columns);

  return (
    <section className="evidence-panel schema-panel">
      <h3>Input schema</h3>
      <p>
        {schema.feature_columns.length} features. The label column is{" "}
        <code>{schema.label_column}</code>.
      </p>
      <details>
        <summary>Inspect all feature fields</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Column</th>
                <th>Type</th>
                <th>Accepted values</th>
              </tr>
            </thead>
            <tbody>
              {schema.feature_columns.map((column) => (
                <tr key={column}>
                  <td>
                    <code>{column}</code>
                  </td>
                  <td>{numeric.has(column) ? "number" : "category"}</td>
                  <td>{schema.categorical_values[column]?.join(", ") ?? "any number"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
