import { EXPORT_FILES, exportFileName, type ExportFile } from "@/lib/exports";

export default function ExportsPage() {
  return (
    <>
      <h1 className="page-title">Exports</h1>
      <ul className="mt-4 space-y-2">
        {(Object.keys(EXPORT_FILES) as ExportFile[]).map((file) => (
          <li key={file}>
            <a href={`/api/admin/exports/${file}`} download className="link">
              {exportFileName(file)}
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}
