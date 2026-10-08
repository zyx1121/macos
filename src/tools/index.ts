import { notesTools } from "./productivity.ts";
import { calendarTools } from "./calendar/index.ts";
import { remindersTools } from "./reminders/index.ts";
import { mailTools } from "./mail/index.ts";
import { safariTools } from "./safari/index.ts";
import { screenshotTools } from "./screenshot/index.ts";

import { organizationTools, planningTools } from "./organization.ts";
import { capabilitiesTool } from "./capabilities.ts";

const domainTools = [
  ...organizationTools,
  ...planningTools,
  ...notesTools,
  ...calendarTools,
  ...remindersTools,
  ...mailTools,
  ...safariTools,
  ...screenshotTools,
];

export const allTools = [...domainTools, capabilitiesTool(domainTools)];
