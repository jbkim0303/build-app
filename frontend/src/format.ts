const krw = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW" });
export const formatKRW = (n: number) => krw.format(n);

// Kickoffs are shown in Korea time regardless of the viewer's locale.
const kst = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Seoul", weekday: "short", day: "numeric", month: "short", year: "numeric",
  hour: "2-digit", minute: "2-digit",
});
export const formatKickoff = (iso: string) => `${kst.format(new Date(iso))} KST`;

const local = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
export const formatDateTime = (iso: string) => local.format(new Date(iso));
