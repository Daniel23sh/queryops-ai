import { useState, type FormEvent } from "react";

import { useCreateDashboard } from "../hooks/useCreateDashboard";

export function CreateDashboardPanel({
  csrfToken,
  onCreated
}: {
  csrfToken: string | null;
  onCreated: () => Promise<void>;
}) {
  const { createPersonalDashboard, errorMessage, status } =
    useCreateDashboard(csrfToken);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const isSaving = status === "saving";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage(null);

    const createdDashboard = await createPersonalDashboard({
      description,
      title
    });

    if (!createdDashboard) {
      return;
    }

    setTitle("");
    setDescription("");
    setSuccessMessage("Personal dashboard created.");
    await onCreated();
  }

  return (
    <section
      className="dashboard-create-panel"
      aria-labelledby="dashboard-create-title"
    >
      <div className="dashboard-section__header">
        <p className="eyebrow">Personal dashboards</p>
        <h2 id="dashboard-create-title">Create personal dashboard</h2>
      </div>

      <form
        className="dashboard-create-form"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <div className="form-field">
          <label htmlFor="dashboard-create-title-input">Dashboard title</label>
          <input
            id="dashboard-create-title-input"
            type="text"
            value={title}
            disabled={isSaving}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>

        <div className="form-field">
          <label htmlFor="dashboard-create-description">Description</label>
          <textarea
            id="dashboard-create-description"
            rows={3}
            value={description}
            disabled={isSaving}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        {errorMessage ? (
          <p className="form-message form-message--error" role="alert">
            {errorMessage}
          </p>
        ) : null}

        {successMessage ? (
          <p className="form-message form-message--success" role="status">
            {successMessage}
          </p>
        ) : null}

        <button
          type="submit"
          className="primary-action-button"
          disabled={isSaving}
        >
          {isSaving ? "Creating..." : "Create dashboard"}
        </button>
      </form>
    </section>
  );
}
