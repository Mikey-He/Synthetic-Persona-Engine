import { fixture } from "@/lib/fixtures";

// Account management as the reference capture lays it out: the projects linked
// to the billing account, and a side panel of principals grouped by role.
export default function AccountPage() {
  const roles = [...new Set(fixture.billingMembers.map((member) => member.role))];

  return (
    <>
      <h1 className="page-title">Account management</h1>
      <div className="mt-4 flex items-start gap-8">
        <section className="min-w-0 flex-1">
          <h2 className="text-[16px] font-medium">Projects linked to this billing account</h2>
          <table className="data-table mt-3">
            <thead>
              <tr>
                <th>Project name</th>
                <th>Project ID</th>
              </tr>
            </thead>
            <tbody>
              {fixture.projects.map((project) => (
                <tr key={project.id}>
                  <td>{project.name}</td>
                  <td>{project.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <aside className="w-[380px] shrink-0 rounded-lg border border-line">
          <h2 className="border-b border-line px-4 py-3 text-[16px] font-medium">{fixture.billingAccount.name}</h2>
          {roles.map((role) => {
            const members = fixture.billingMembers.filter((member) => member.role === role);
            return (
              <section key={role} className="border-b border-line px-4 py-3 last:border-b-0">
                <h3 className="font-medium">
                  {role} ({members.length})
                </h3>
                <ul className="mt-1">
                  {members.map((member) => (
                    <li key={member.id} className="py-1">
                      <div>
                        {member.name}
                        {member.isYou ? " (you)" : ""}
                      </div>
                      <div className="text-[13px] text-muted">{member.email}</div>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </aside>
      </div>
    </>
  );
}
