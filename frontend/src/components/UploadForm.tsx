import { useState, type FormEvent } from "react";
import type { Provider } from "../api";
import "./UploadForm.css";

type Props = {
  onSubmit: (files: File[], provider: Provider) => void;
  disabled: boolean;
};

export function UploadForm({ onSubmit, disabled }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [provider, setProvider] = useState<Provider>("mock");
  const [error, setError] = useState<string | null>(null);

  const handleFiles = (list: FileList | null) => {
    if (!list) return;
    const picked = Array.from(list);
    const nonCsv = picked.filter((f) => !f.name.toLowerCase().endsWith(".csv"));
    if (nonCsv.length) {
      setError(`not a .csv file: ${nonCsv.map((f) => f.name).join(", ")}`);
      return;
    }
    setError(null);
    setFiles(picked);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (files.length === 0) {
      setError("choose at least one CSV file");
      return;
    }
    onSubmit(files, provider);
  };

  return (
    <form className="upload-form" onSubmit={submit}>
      <label className="field">
        <span className="field-label">Dataset (one or more CSVs, one table per file)</span>
        <input
          type="file"
          accept=".csv"
          multiple
          disabled={disabled}
          onChange={(e) => handleFiles(e.target.files)}
        />
        {files.length > 0 && (
          <ul className="file-list">
            {files.map((f) => (
              <li key={f.name}>
                {f.name} <span className="ink-muted">({(f.size / 1024).toFixed(0)} KB)</span>
              </li>
            ))}
          </ul>
        )}
      </label>

      <label className="field">
        <span className="field-label">Provider</span>
        <select value={provider} disabled={disabled} onChange={(e) => setProvider(e.target.value as Provider)}>
          <option value="mock">mock (no API key needed, demo scenario)</option>
          <option value="anthropic">anthropic</option>
          <option value="openai">openai</option>
        </select>
      </label>

      {error && <p className="form-error" role="alert">{error}</p>}

      <button type="submit" disabled={disabled}>
        {disabled ? "Running..." : "Generate report"}
      </button>
    </form>
  );
}
