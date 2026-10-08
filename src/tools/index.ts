import { notesTools } from "./productivity.ts";
import { calendarTools } from "./calendar/index.ts";
import { remindersTools } from "./reminders/index.ts";
import { mailTools } from "./mail/index.ts";
import { safariTools } from "./safari/index.ts";
import { screenshotTools } from "./screenshot/index.ts";

export const allTools = [
  ...notesTools,
  ...calendarTools,
  ...remindersTools,
  ...mailTools,
  ...safariTools,
  ...screenshotTools,
];
