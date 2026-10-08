export function sleepWindow(start: string, end: string, wakeDate: string, timezone: string) {
  const wall = (stamp: string) => {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(stamp));
    const pick = (type: string) => parts.find(p => p.type === type)!.value;
    const day = `${pick("year")}-${pick("month")}-${pick("day")}`;
    return (Date.parse(day + "T00:00:00Z") - Date.parse(wakeDate + "T00:00:00Z")) / 86400000 * 24 + Number(pick("hour")) + Number(pick("minute")) / 60;
  };
  return [wall(start), wall(end)] as const;
}
