import { METRIC_GROUPS } from "../../features/biometrics/groups";

export const SEARCH_TABS = [
  ...["profile", "appearance", "devices", "notifications", "data-health", "account"].map(tab => ({ to: `/app/settings?tab=${tab}`, key: ({ profile: "settings.profile", appearance: "settings.theme_section", devices: "settings.devices", notifications: "lab.notification_preferences", "data-health": "lab.data_health", account: "settings.account" } as Record<string, string>)[tab], parent: "nav.settings" })),
  ...["baselines", "experiments", "nutrition", "labs", "documents", "outcomes", "reports"].map(tab => ({ to: `/app/lab?tab=${tab}`, key: `lab.${tab}`, parent: "lab.nav" })),
  ...[{ tab: "plan", key: "design.today_plan" }, { tab: "calendar", key: "training.calendar" }, { tab: "load", key: "design.training_load" }].map(x => ({ to: `/app/training?tab=${x.tab}`, key: x.key, parent: "nav.training" })),
  { to: "/app/biometrics?tab=favorites", key: "completion.favorites", parent: "nav.biometrics" },
  { to: "/app/biometrics?tab=labs", key: "biometrics.labs", parent: "nav.biometrics" },
  ...METRIC_GROUPS.flatMap(category => category.groups.map(group => ({ to: `/app/biometrics?tab=${category.value}&group=${group.value}`, key: group.label, parent: category.label }))),
];

export function searchText(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}
