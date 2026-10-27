"use client";

import { useRouter } from "next/navigation";

// Goes back in history when there is somewhere to go back to, otherwise
// follows the fallback link, so the link is never dead.
export function BackLink({ fallbackHref }: { fallbackHref: string }) {
  const router = useRouter();
  return (
    <a
      href={fallbackHref}
      className="link"
      onClick={(event) => {
        if (window.history.length > 1) {
          event.preventDefault();
          router.back();
        }
      }}
    >
      Back
    </a>
  );
}
