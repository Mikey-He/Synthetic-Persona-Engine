import { parseNumber } from "@/lib/domain/rules";
import type { BudgetConfig, Trigger } from "@/lib/domain/types";
import type { Change, FormState } from "./formStore";

// Field setters shared by both create flows, so A and B write a setting the
// same way. Each keeps the raw text of number fields beside the parsed value.

type Texts = Pick<FormState, "targetText" | "percentTexts">;

export function setTarget(change: Change, text: string) {
  change([["amount.target", parseNumber(text)]], { targetText: text });
}

export function setPercent(change: Change, { percentTexts }: Texts, index: number, percent: number, text: string) {
  change([[`thresholds.${index}.percent`, percent]], {
    percentTexts: percentTexts.map((t, i) => (i === index ? text : t)),
  });
}

export function setTrigger(change: Change, index: number, trigger: Trigger) {
  change([[`thresholds.${index}.trigger`, trigger]]);
}

export function removeThreshold(change: Change, config: BudgetConfig, { percentTexts }: Texts, index: number) {
  change([["thresholds", config.thresholds.filter((_, i) => i !== index)]], {
    percentTexts: percentTexts.filter((_, i) => i !== index),
  });
}

// A new rule starts at 0% of actual spend, as in the reference capture.
export function addThreshold(change: Change, config: BudgetConfig, { percentTexts }: Texts) {
  change([["thresholds", [...config.thresholds, { percent: 0, trigger: "actual" }]]], {
    percentTexts: [...percentTexts, "0"],
  });
}
