"use client";

import { useSyncExternalStore } from "react";

const MIN_WIDTH = 1440;
const MIN_HEIGHT = 900;

function subscribe(onChange: () => void) {
  window.addEventListener("resize", onChange);
  return () => window.removeEventListener("resize", onChange);
}

// A string snapshot stays equal between reads, so React does not loop.
const readSize = () => `${window.innerWidth}x${window.innerHeight}`;
const readNothingOnServer = () => null;

export function ViewportGate() {
  const size = useSyncExternalStore(subscribe, readSize, readNothingOnServer);
  if (size === null) return null;

  const [width, height] = size.split("x").map(Number);
  if (width >= MIN_WIDTH && height >= MIN_HEIGHT) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-white px-8">
      <p className="max-w-xl text-center text-[16px] leading-6">
        Please make this window larger. It needs to be at least {MIN_WIDTH} by {MIN_HEIGHT}.
        Current size is {width} by {height}.
      </p>
    </div>
  );
}
