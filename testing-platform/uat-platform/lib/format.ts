const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatMoney(value: number, currency: string, digits = 2) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

// "2026-04" -> "Apr 2026". String based, so no clock or time zone is involved.
export function monthLabel(month: string) {
  const [year, m] = month.split("-");
  return `${MONTHS[Number(m) - 1]} ${year}`;
}

const LONG_MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Last day of a "2026-09" month. Calendar arithmetic only, never the clock.
const lastDayOf = (year: number, month: number) => new Date(Date.UTC(year, month, 0)).getUTCDate();

// "2026-04", "2026-09" -> "April 1, 2026 – September 30, 2026"
export function monthRangeLabel(first: string, last: string) {
  const [fy, fm] = first.split("-").map(Number);
  const [ly, lm] = last.split("-").map(Number);
  return `${LONG_MONTHS[fm - 1]} 1, ${fy} – ${LONG_MONTHS[lm - 1]} ${lastDayOf(ly, lm)}, ${ly}`;
}

// "2026-09" -> "September 1 – 30, 2026"
export function monthSpanLabel(month: string) {
  const [year, m] = month.split("-").map(Number);
  return `${LONG_MONTHS[m - 1]} 1 – ${lastDayOf(year, m)}, ${year}`;
}
