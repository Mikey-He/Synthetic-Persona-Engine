import { BackLink } from "@/components/console/BackLink";

type Props = { params: Promise<{ token: string; area: string }> };

export default async function StubPage({ params }: Props) {
  const { token, area } = await params;
  return (
    <>
      <p>
        {area === "notification-channels"
          ? "Notification channels are outside this study."
          : "This page is not part of the study."}
      </p>
      <p className="mt-4">
        <BackLink fallbackHref={`/s/${token}/billing`} />
      </p>
    </>
  );
}
