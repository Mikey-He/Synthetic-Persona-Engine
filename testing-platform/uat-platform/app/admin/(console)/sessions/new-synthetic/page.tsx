import { NewSyntheticSessionForm } from "@/components/admin/forms";

export default function NewSyntheticSessionPage() {
  return (
    <>
      <h1 className="page-title">New synthetic session</h1>
      <div className="mt-6">
        <NewSyntheticSessionForm />
      </div>
    </>
  );
}
