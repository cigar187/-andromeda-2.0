// AndromedaCard — RN port of 5thBase/src/screens/AndromedaScreen.js AndromedaCard.
// LinearGradient/Ionicons are NOT installed in this app, so:
//   - left rail = solid color (still shows direction)
//   - DETAILS expand uses a text chevron
// Contract matches 5thBase's version so the assembler on the droplet is the same shape.
import React, { useMemo, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { M31Colors, M31Space } from "../theme/m31.js";

function renderLead(str) {
  const parts = String(str || "").split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return (
        <Text key={i} style={{ color: M31Colors.ink, fontWeight: "700" }}>
          {p.slice(2, -2)}
        </Text>
      );
    }
    return <Text key={i}>{p}</Text>;
  });
}

const BRIEF_TONES = {
  k:   { color: M31Colors.ink,   fontWeight: "700" },
  up:  { color: M31Colors.over,  fontWeight: "700" },
  dn:  { color: M31Colors.under, fontWeight: "700" },
  cau: { color: M31Colors.warn,  fontWeight: "700" },
};
function renderBrief(str) {
  const parts = String(str || "").split(/(\{\{[a-z]+:[^}]+\}\})/g);
  return parts.map((p, i) => {
    const m = p.match(/^\{\{([a-z]+):([\s\S]+)\}\}$/);
    if (m) {
      const style = BRIEF_TONES[m[1]] || null;
      return <Text key={i} style={style}>{m[2]}</Text>;
    }
    return <Text key={i}>{p}</Text>;
  });
}

function railColor(direction, isAlert) {
  if (isAlert) return M31Colors.news;
  if (direction === "over") return M31Colors.over;
  return M31Colors.under;
}

function dotColor(key) {
  const k = String(key || "");
  if (k.includes("STATS")) return M31Colors.stats;
  if (k.includes("MONEY")) return M31Colors.money;
  if (k.includes("NEWS"))  return M31Colors.news;
  return M31Colors.ink3;
}

const STREAM_COLOR = {
  stats: M31Colors.stats,
  money: M31Colors.money,
  news:  M31Colors.news,
};

function DriverChip({ item }) {
  const isDriver = item.tone && item.tone.startsWith("driver");
  const isWarn = item.tone === "warn";
  if (isWarn) {
    return (
      <View style={[s.chip, s.chipWarn]}>
        <Text style={s.chipWarnText}>{`⚠ ${item.key}`}</Text>
      </View>
    );
  }
  return (
    <View style={[s.chip, isDriver && s.chipDriver]}>
      <View style={[s.chipDot, { backgroundColor: dotColor(item.key) }]} />
      <Text style={[s.chipText, isDriver && { color: M31Colors.ink }]}>{item.key}</Text>
    </View>
  );
}

function PropTile({ label, value, sub, valueTone }) {
  const tone = valueTone === "pos" ? { color: M31Colors.over }
              : valueTone === "neg" ? { color: M31Colors.under }
              : null;
  return (
    <View style={s.tile}>
      <Text style={s.tileLabel}>{label}</Text>
      <Text style={[s.tileValue, tone]}>{value}</Text>
      <Text style={s.tileSub}>{sub}</Text>
    </View>
  );
}

function SimBlock({ small, big, lab }) {
  return (
    <View style={s.simCell}>
      <Text style={s.simSmall}>{small}</Text>
      <Text style={s.simBig}>{big}</Text>
      <Text style={s.simLab}>{lab}</Text>
    </View>
  );
}

function StreamRow({ label, kind, fill, read }) {
  const clamped = Math.max(0, Math.min(1, Number(fill) || 0));
  return (
    <View style={s.streamRow}>
      <Text style={s.streamLbl}>{label}</Text>
      <View style={s.streamTrack}>
        <View style={[s.streamFill, { width: `${(clamped * 100).toFixed(1)}%`, backgroundColor: STREAM_COLOR[kind] }]} />
      </View>
      <Text style={s.streamRead}>{read}</Text>
    </View>
  );
}

export function AndromedaCard({ card, initiallyOpen }) {
  const [open, setOpen] = useState(!!initiallyOpen);
  const rail = useMemo(() => railColor(card.direction, card.isAlert), [card.direction, card.isAlert]);
  const isOver = card.direction === "over";

  return (
    <View style={[s.card, card.isAlert && s.cardAlert]}>
      <View style={[s.cardRail, { backgroundColor: rail }]} />

      <View style={s.cardTop}>
        <View style={{ flex: 1, paddingRight: 10 }}>
          <Text style={s.cardName}>{card.pitcherName}</Text>
          <Text style={s.cardMatch}>
            {card.team} vs {card.opponent} · <Text style={{ color: M31Colors.cyan, fontWeight: "700" }}>
              {card.statCategory} {card.line}
            </Text>
          </Text>
        </View>
        <View style={s.verdict}>
          <View style={[s.badge, {
            borderColor: isOver ? M31Colors.overBorder : M31Colors.underBorder,
            backgroundColor: isOver ? M31Colors.overA08 : M31Colors.underA08,
          }]}>
            <Text style={{ color: isOver ? M31Colors.over : M31Colors.under, fontWeight: "800", fontSize: 12, letterSpacing: 0.6 }}>
              {isOver ? "▲ OVER" : "▼ UNDER"}
            </Text>
          </View>
          <Text style={s.conf}>
            conviction <Text style={{ color: M31Colors.ink2 }}>{card.conviction}</Text>
          </Text>
        </View>
      </View>

      <View style={s.drivers}>
        {(card.drivers || []).map((d, i) => <DriverChip key={`${d.key}-${i}`} item={d} />)}
        {card.regressionWarn && <DriverChip item={{ key: "REGRESSION", tone: "warn" }} />}
      </View>

      <Text style={s.lead}>{renderLead(card.lead || "")}</Text>

      <View style={s.tiles}>
        <PropTile
          label="K PROJ"
          value={typeof card.kProj === "number" ? card.kProj.toFixed(2) : "—"}
          sub={`line ${card.line}`}
          valueTone={isOver ? "pos" : "neg"}
        />
        <PropTile label="EDGE" value={String(card.edgeScore ?? "—")} sub={card.edgeBand || ""} />
        <PropTile
          label="BOOKS"
          value={`${card.booksAgreeNum ?? 0}/${card.booksAgreeDen ?? 0}`}
          sub={card.booksLabel || ""}
        />
      </View>

      {typeof card.simFloor === "number" && (
        <View style={s.sim}>
          <SimBlock small="FLOOR"   big={card.simFloor.toFixed(1)}   lab="under" />
          <SimBlock small="MEDIAN"  big={card.simMedian.toFixed(1)}  lab="at line" />
          <SimBlock small="CEILING" big={card.simCeiling.toFixed(1)} lab="over" />
        </View>
      )}

      {open && (
        <View style={s.more}>
          <Text style={s.why}>{renderBrief(card.brief || "")}</Text>
          {card.stats && <StreamRow label="STATS" kind="stats" fill={card.stats.fill} read={card.stats.read} />}
          {card.money && <StreamRow label="MONEY" kind="money" fill={card.money.fill} read={card.money.read} />}
          {card.news  && <StreamRow label="NEWS"  kind="news"  fill={card.news.fill}  read={card.news.read} />}
          <View style={s.addon}>
            <Text style={s.addonText}>
              ＋ room for more — new modules drop in here, no app update needed
            </Text>
          </View>
        </View>
      )}

      <TouchableOpacity activeOpacity={0.85} onPress={() => setOpen(v => !v)} style={s.expand}>
        <Text style={s.expandText}>{open ? "COLLAPSE ▲" : "DETAILS ▼"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const CARD_X = M31Space.cardX;
const CARD_PAD = M31Space.cardPad;

const s = StyleSheet.create({
  card: {
    position: "relative",
    marginHorizontal: CARD_X,
    marginTop: 14,
    borderRadius: 20,
    padding: CARD_PAD,
    paddingBottom: 0,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: M31Colors.line,
    backgroundColor: M31Colors.surface,
  },
  cardAlert: { borderColor: M31Colors.alertBorder },
  cardRail: { position: "absolute", left: 0, top: 0, bottom: 0, width: 4 },

  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 10 },
  cardName: { fontSize: 19, fontWeight: "800", color: M31Colors.ink, lineHeight: 22 },
  cardMatch: { fontSize: 11.5, color: M31Colors.ink2, marginTop: 5, letterSpacing: 0.12 },

  verdict: { alignItems: "flex-end", gap: 6 },
  badge: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 11, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  conf: { fontSize: 10.5, color: M31Colors.ink3, letterSpacing: 0.2 },

  drivers: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 13 },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 9,
    borderWidth: 1, borderColor: M31Colors.line, backgroundColor: M31Colors.surface2,
  },
  chipDriver: { borderColor: M31Colors.driverBorder, backgroundColor: M31Colors.driverA10 },
  chipWarn: { borderColor: M31Colors.warnBorder, backgroundColor: M31Colors.warnA10 },
  chipDot: { width: 7, height: 7, borderRadius: 999 },
  chipText: { fontSize: 10.5, fontWeight: "800", letterSpacing: 0.3, color: M31Colors.ink2 },
  chipWarnText: { fontSize: 10.5, fontWeight: "800", letterSpacing: 0.3, color: M31Colors.warnText },

  lead: { marginTop: 13, fontSize: 13.5, lineHeight: 20, color: M31Colors.ink2 },

  tiles: { flexDirection: "row", gap: 8, marginTop: 13 },
  tile: {
    flex: 1, backgroundColor: M31Colors.surface2, borderWidth: 1, borderColor: M31Colors.line,
    borderRadius: 12, paddingHorizontal: 10, paddingVertical: 9,
  },
  tileLabel: { fontSize: 9.5, letterSpacing: 1.045, color: M31Colors.ink3, fontWeight: "800" },
  tileValue: { fontSize: 18, fontWeight: "800", color: M31Colors.ink, marginTop: 1, marginBottom: 1 },
  tileSub: { fontSize: 10, color: M31Colors.ink3, fontWeight: "600" },

  more: {},
  why: { marginTop: 14, fontSize: 14.5, lineHeight: 23, color: M31Colors.whyText },

  sim: { flexDirection: "row", gap: 8, marginTop: 14 },
  simCell: {
    flex: 1, borderWidth: 1, borderStyle: "dashed", borderColor: M31Colors.simDashed,
    borderRadius: 11, paddingHorizontal: 6, paddingVertical: 8, alignItems: "center",
  },
  simSmall: { fontSize: 9, letterSpacing: 0.9, color: M31Colors.ink3, fontWeight: "800" },
  simBig: { fontSize: 16, fontWeight: "800", color: M31Colors.ink, marginTop: 2 },
  simLab: { fontSize: 8.5, color: M31Colors.ink3, fontWeight: "700" },

  streamRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 9 },
  streamLbl: { width: 50, fontSize: 10.5, letterSpacing: 0.945, color: M31Colors.ink3, fontWeight: "800" },
  streamTrack: { flex: 1, height: 7, borderRadius: 999, backgroundColor: M31Colors.trackBg, overflow: "hidden" },
  streamFill: { height: "100%", borderRadius: 999 },
  streamRead: { width: 66, fontSize: 11, color: M31Colors.ink2, fontWeight: "700", textAlign: "right" },

  addon: {
    marginTop: 13, borderWidth: 1, borderStyle: "dashed", borderColor: M31Colors.addonDashed,
    borderRadius: 12, padding: 11, alignItems: "center",
  },
  addonText: { fontSize: 10.5, color: M31Colors.ink3, fontWeight: "700", letterSpacing: 0.525, textAlign: "center" },

  expand: {
    marginTop: 14, marginHorizontal: -CARD_PAD, paddingVertical: 11,
    borderTopWidth: 1, borderTopColor: M31Colors.line,
    flexDirection: "row", alignItems: "center", justifyContent: "center",
  },
  expandText: { fontSize: 10.5, fontWeight: "800", letterSpacing: 1.47, color: M31Colors.cyan },
});
