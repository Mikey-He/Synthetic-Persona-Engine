import { NewHumanSessionForm } from "@/components/admin/forms";

export default function NewHumanSessionPage() {
  return (
    <>
      <h1 className="page-title">New human session</h1>
      <p className="mt-2 text-muted">
        The participant is stored under a random ID. Never record a name or an email.
      </p>
      <div className="mt-6">
        <NewHumanSessionForm />
      </div>
    </>
  );
}
