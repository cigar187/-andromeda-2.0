// Home — landing screen. Fetches today's slate summary and shows:
//   - Date + weekday header
//   - 4-tile row: STARTERS · ALERTS · COIN-FLIPS · TOP EDGE
//   - Top-3 highest-edge plays (mini cards)
//   - "READ THE FEED" CTA that jumps to the ANDROMEDA tab
// Everything derived from the same /api/andromeda/today?sport=mlb the ANDROMEDA feed uses.
import React, { useEffect, useState, useMemo } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, StyleSheet } from "react-native";
import { M31Colors } from "../theme/m31.js";
import { API_BASE_URL, API_TOKEN } from "../config/api.js";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function fmtHeaderDate(d = new Date()) {
  return `${WEEKDAYS[d.getDay()]} · ${MONTHS[d.getMonth()]} ${d.getDate()} · ${d.getFullYear()}`;
}

export function Home({ onEnterFeed }) {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const url = `${API_BASE_URL}/api/andromeda/today?sport=mlb`;
    const headers = API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {};
    setLoading(true);
    setError(null);
    fetch(url, { headers })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((body) => {
        if (cancelled) return;
        setCards(Array.isArray(body.verdicts) ? body.verdicts : []);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e.message || e));
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const stats = useMemo(() => {
    if (!cards.length) return { starters: 0, alerts: 0, coinFlips: 0, topEdge: null, top3: [] };
    // Distinct pitchers (one card can have multiple lines per pitcher)
    const pitcherSet = new Set(cards.map((c) => c.pitcherName));
    const alerts = cards.filter((c) => c.isAlert).length;
    const coinFlips = cards.filter((c) => c.no_edge_dead_zone).length;
    const topEdge = cards.reduce((mx, c) => Math.max(mx, c.edgeScore || 0), 0);
    const sorted = [...cards].sort((a, b) => (b.edgeScore || 0) - (a.edgeScore || 0));
    const top3 = sorted.slice(0, 3);
    return { starters: pitcherSet.size, alerts, coinFlips, topEdge, top3 };
  }, [cards]);

  return (
    <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
      <View style={s.head}>
        <Text style={s.kick}>TODAY'S BOARD</Text>
        <Text style={s.date}>{fmtHeaderDate()}</Text>
      </View>

      {loading ? (
        <View style={s.empty}>
          <ActivityIndicator color={M31Colors.cyan} />
          <Text style={[s.emptyTitle, { marginTop: 12 }]}>Reading the board…</Text>
        </View>
      ) : error ? (
        <View style={s.empty}>
          <Text style={s.emptyTitle}>Backend unreachable</Text>
          <Text style={s.emptyBody}>{error}</Text>
        </View>
      ) : (
        <>
          {/* Stat tile row */}
          <View style={s.tiles}>
            <StatTile label="STARTERS" value={String(stats.starters)} tone="cyan" />
            <StatTile label="ALERTS" value={String(stats.alerts)} tone={stats.alerts > 0 ? "news" : "muted"} />
            <StatTile label="COIN FLIPS" value={String(stats.coinFlips)} tone={stats.coinFlips > 0 ? "warn" : "muted"} />
            <StatTile label="TOP EDGE" value={stats.topEdge != null ? String(stats.topEdge) : "—"} tone="over" />
          </View>

          {/* Top-3 highest edge */}
          {stats.top3.length > 0 && (
            <>
              <Text style={s.sectionLabel}>TOP EDGE — TONIGHT</Text>
              {stats.top3.map((c) => <TopCardMini key={c.id} card={c} />)}
            </>
          )}

          {/* Alerts callout, if any */}
          {stats.alerts > 0 && (
            <View style={s.alertBox}>
              <Text style={s.alertLabel}>{stats.alerts} ALERT{stats.alerts > 1 ? "S" : ""}</Text>
              <Text style={s.alertBody}>Sharp market plus retail-book agreement above threshold. Open ANDROMEDA to review.</Text>
            </View>
          )}

          {/* CTA */}
          <Pressable style={s.cta} onPress={onEnterFeed} accessibilityRole="button">
            <Text style={s.ctaText}>READ THE FEED  →</Text>
          </Pressable>

          <Text style={s.footNote}>MLB only at launch — other sports light up as feeds wire in.</Text>
        </>
      )}
    </ScrollView>
  );
}

function StatTile({ label, value, tone }) {
  const color = tone === "over" ? M31Colors.over
              : tone === "news" ? M31Colors.news
              : tone === "warn" ? M31Colors.warn
              : tone === "cyan" ? M31Colors.cyan
              : M31Colors.ink;
  return (
    <View style={s.tile}>
      <Text style={s.tileLabel}>{label}</Text>
      <Text style={[s.tileValue, { color }]}>{value}</Text>
    </View>
  );
}

function TopCardMini({ card }) {
  const isOver = card.direction === "over";
  const arrow = isOver ? "▲" : "▼";
  const dirColor = isOver ? M31Colors.over : M31Colors.under;
  return (
    <View style={s.mini}>
      <View style={[s.miniRail, { backgroundColor: dirColor }]} />
      <View style={{ flex: 1 }}>
        <Text style={s.miniName}>{card.pitcherName}</Text>
        <Text style={s.miniSub}>
          {card.team} vs {card.opponent} · {card.statCategory} {card.line}
        </Text>
      </View>
      <View style={s.miniRight}>
        <Text style={[s.miniDir, { color: dirColor }]}>{arrow} {isOver ? "OVER" : "UNDER"}</Text>
        <Text style={s.miniEdge}>edge {card.edgeScore}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  scroll: { paddingBottom: 40, backgroundColor: M31Colors.bg, minHeight: "100%" },

  head: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 6 },
  kick: { fontSize: 12, fontWeight: "800", letterSpacing: 2.16, color: M31Colors.ink3 },
  date: { fontSize: 22, fontWeight: "800", letterSpacing: 0.4, color: M31Colors.ink, marginTop: 5 },

  tiles: { flexDirection: "row", flexWrap: "wrap", gap: 8, paddingHorizontal: 16, marginTop: 16 },
  tile: {
    flexGrow: 1, flexBasis: "45%", minWidth: 100,
    backgroundColor: M31Colors.surface, borderWidth: 1, borderColor: M31Colors.line,
    borderRadius: 14, paddingVertical: 14, paddingHorizontal: 14, alignItems: "center",
  },
  tileLabel: { fontSize: 10, fontWeight: "800", letterSpacing: 1.2, color: M31Colors.ink3 },
  tileValue: { fontSize: 28, fontWeight: "800", marginTop: 6 },

  sectionLabel: {
    fontSize: 11, fontWeight: "800", letterSpacing: 1.84, color: M31Colors.ink3,
    marginTop: 22, marginHorizontal: 20, marginBottom: 8,
  },

  mini: {
    marginHorizontal: 16, marginTop: 8, borderRadius: 14, borderWidth: 1, borderColor: M31Colors.line,
    backgroundColor: M31Colors.surface, padding: 12, paddingLeft: 16,
    flexDirection: "row", alignItems: "center", gap: 12, overflow: "hidden",
    position: "relative",
  },
  miniRail: { position: "absolute", left: 0, top: 0, bottom: 0, width: 3 },
  miniName: { fontSize: 15, fontWeight: "800", color: M31Colors.ink },
  miniSub: { fontSize: 11.5, color: M31Colors.ink2, marginTop: 3 },
  miniRight: { alignItems: "flex-end", gap: 3 },
  miniDir: { fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  miniEdge: { fontSize: 10, fontWeight: "800", color: M31Colors.ink3, letterSpacing: 0.3 },

  alertBox: {
    marginHorizontal: 16, marginTop: 20, borderRadius: 12, borderWidth: 1, borderColor: M31Colors.alertBorder,
    backgroundColor: "rgba(245, 166, 35, 0.06)", padding: 14,
  },
  alertLabel: { fontSize: 12, fontWeight: "800", letterSpacing: 2.16, color: M31Colors.news },
  alertBody: { fontSize: 12.5, color: M31Colors.ink2, marginTop: 6, lineHeight: 18 },

  cta: {
    marginHorizontal: 16, marginTop: 24, height: 52, borderRadius: 14,
    borderWidth: 1, borderColor: M31Colors.cyan, backgroundColor: M31Colors.cyanA16,
    alignItems: "center", justifyContent: "center",
  },
  ctaText: { color: M31Colors.cyan, fontSize: 14, fontWeight: "800", letterSpacing: 1.4 },

  footNote: { marginTop: 20, textAlign: "center", fontSize: 11, color: M31Colors.ink3, letterSpacing: 0.4 },

  empty: {
    marginHorizontal: 16, marginTop: 40, padding: 24, borderRadius: 18,
    borderWidth: 1, borderStyle: "dashed", borderColor: M31Colors.line, alignItems: "center",
  },
  emptyTitle: { fontSize: 15, fontWeight: "800", color: M31Colors.ink2, letterSpacing: 0.3 },
  emptyBody: { marginTop: 8, fontSize: 12.5, color: M31Colors.ink3, textAlign: "center", lineHeight: 18 },
});
