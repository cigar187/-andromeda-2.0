// Design tokens ported from the browser skin's :root vars — one authoritative source.
export const T = {
  bg: "#0b0e13",
  panel: "#11171d",
  panel2: "#172027",
  text: "#e8eee9",
  muted: "#93a09f",
  faint: "#65716f",
  line: "#2a363b",
  accent: "#8bd3ab",
  warn: "#d5ad61",
  danger: "#d98989",
  radius: 12,
};

export const statusColor = (status) => {
  const s = (status || "").toLowerCase();
  if (s === "ready") return { fg: T.accent, border: "#356951", bg: "#3473522e" };
  if (s === "watch") return { fg: T.warn, border: "#715d37", bg: "#8c6c2e24" };
  return { fg: T.faint, border: T.line, bg: "transparent" };
};
