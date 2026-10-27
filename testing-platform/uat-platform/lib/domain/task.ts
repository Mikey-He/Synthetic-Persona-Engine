export const TASK_VERSION = "task-v1";

// Word for word from docs/design-guide-v2.md Part 3. Paragraphs are separated
// by a blank line. Changing this text means a new TASK_VERSION and a guide update.
export const TASK_TEXT = [
  "You manage your team's cloud spending. Create a fixed monthly budget of $1,000 for the Atlas project. The budget should reset at the start of each calendar month. Include all Atlas project costs and exclude costs from other projects.",
  "Configure an email alert for when the project's actual spending during the month exceeds 80% of the budget. Only the Atlas project owner should receive this alert.",
  "Save your settings and indicate when you have finished.",
].join("\n\n");
