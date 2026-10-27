import { db } from "@/lib/db";

const BANDS = ["low", "medium", "high", "none"] as const;
const LABELS = ["pilot", "calibration_A", "evaluation_A", "evaluation_B", "synthetic"] as const;
const VARIANTS = ["A", "B"] as const;

export default async function AssignmentPage() {
  const sessions = await db.session.findMany({
    select: { variant: true, datasetLabel: true, participant: { select: { familiarityBand: true } } },
  });
  const count = (variant: string, band: string, label: string) =>
    sessions.filter(
      (s) =>
        s.variant === variant &&
        s.datasetLabel === label &&
        (s.participant?.familiarityBand ?? "none") === band,
    ).length;

  return (
    <>
      <h1 className="page-title">Assignment</h1>
      {VARIANTS.map((variant) => (
        <section key={variant} className="mt-6">
          <h2 className="text-[16px] font-medium">Variant {variant}</h2>
          <table className="data-table mt-2 max-w-4xl">
            <thead>
              <tr>
                <th>Familiarity band</th>
                {LABELS.map((label) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {BANDS.map((band) => (
                <tr key={band}>
                  <td>{band}</td>
                  {LABELS.map((label) => (
                    <td key={label}>{count(variant, band, label)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}
