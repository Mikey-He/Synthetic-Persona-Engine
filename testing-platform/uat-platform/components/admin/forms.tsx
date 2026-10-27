"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

// Researcher console controls. None of them asks for a name or an email.

type Created = { link: string; variant: string };

function CopyLink({ link, variant }: Created) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-6 max-w-2xl rounded-lg border border-line p-4">
      <p className="font-medium">Participant link · variant {variant}</p>
      <div className="mt-2 flex gap-2">
        <input readOnly value={link} aria-label="Participant link" className="field flex-1" />
        <button
          type="button"
          className="btn-secondary"
          onClick={async () => {
            await navigator.clipboard.writeText(link);
            setCopied(true);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

async function createSession(body: Record<string, unknown>) {
  const response = await fetch("/api/admin/sessions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Session not created (${response.status}).`);
  return (await response.json()) as Created;
}

function useCreate() {
  const [created, setCreated] = useState<Created | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submit = (read: (form: FormData) => Record<string, unknown>) => async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      setCreated(await createSession(read(new FormData(event.currentTarget))));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return { created, error, submit };
}

type SelectProps = {
  name: string;
  label: string;
  options: string[];
  optionLabels?: Record<string, string>;
  onChange?: (value: string) => void;
};

const Select = ({ name, label, options, optionLabels = {}, onChange }: SelectProps) => (
  <label className="block">
    <span className="block font-medium">{label}</span>
    <select name={name} className="field mt-1.5 w-96" onChange={(event) => onChange?.(event.target.value)}>
      {options.map((option) => (
        <option key={option} value={option}>
          {optionLabels[option] ?? option}
        </option>
      ))}
    </select>
  </label>
);

const Text = ({ name, label, required = true }: { name: string; label: string; required?: boolean }) => (
  <label className="block">
    <span className="block font-medium">{label}</span>
    <input name={name} required={required} className="field mt-1.5 w-72" />
  </label>
);

export function NewHumanSessionForm() {
  const { created, error, submit } = useCreate();
  const [label, setLabel] = useState("pilot");
  return (
    <>
      <form
        className="space-y-4"
        onSubmit={submit((form) => ({
          actorType: "human",
          familiarityBand: form.get("familiarityBand"),
          datasetLabel: form.get("datasetLabel"),
          ...(label === "pilot" ? { variant: form.get("variant") } : {}),
        }))}
      >
        <Select name="familiarityBand" label="Familiarity band" options={["low", "medium", "high"]} />
        <Select
          name="datasetLabel"
          label="Dataset label"
          options={["pilot", "calibration_A", "evaluation"]}
          optionLabels={{ evaluation: "evaluation_A or evaluation_B (block assignment)" }}
          onChange={setLabel}
        />
        {label === "pilot" ? (
          <Select name="variant" label="Variant" options={["A", "B"]} />
        ) : (
          <div>
            <span className="block font-medium">Variant</span>
            <p className="mt-1.5">
              {label === "calibration_A" ? "A" : "Assigned in blocks of two within the familiarity band"}
            </p>
          </div>
        )}
        <button type="submit" className="btn-primary">
          Create session
        </button>
      </form>
      {error && <p className="mt-4 text-error">{error}</p>}
      {created && <CopyLink {...created} />}
    </>
  );
}

export function NewSyntheticSessionForm() {
  const { created, error, submit } = useCreate();
  return (
    <>
      <form
        className="space-y-4"
        onSubmit={submit((form) => ({
          actorType: "synthetic",
          modelId: form.get("modelId"),
          promptVersion: form.get("promptVersion"),
          personaId: form.get("personaId"),
          calibrationId: (form.get("calibrationId") as string).trim() || null,
          variant: form.get("variant"),
        }))}
      >
        <Text name="modelId" label="Model ID" />
        <Text name="promptVersion" label="Prompt version" />
        <Text name="personaId" label="Persona ID" />
        <Text name="calibrationId" label="Calibration ID (optional)" required={false} />
        <Select name="variant" label="Variant" options={["A", "B"]} />
        <div>
          <span className="block font-medium">Dataset label</span>
          <p className="mt-1.5">synthetic</p>
        </div>
        <button type="submit" className="btn-primary">
          Create session
        </button>
      </form>
      {error && <p className="mt-4 text-error">{error}</p>}
      {created && <CopyLink {...created} />}
    </>
  );
}

export function EndSessionButton({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      className="btn-secondary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await fetch(`/api/admin/sessions/${sessionId}/end`, { method: "POST" });
        router.refresh();
      }}
    >
      End session
    </button>
  );
}

export function RescoreButton() {
  const router = useRouter();
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        className="btn-secondary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const response = await fetch("/api/admin/rescore", { method: "POST" });
          const body = (await response.json()) as { sessions: number; evaluatorVersion: string };
          setResult(`Re-scored ${body.sessions} sessions with ${body.evaluatorVersion}.`);
          setBusy(false);
          router.refresh();
        }}
      >
        Re-score
      </button>
      {result && <span className="text-muted">{result}</span>}
    </div>
  );
}
