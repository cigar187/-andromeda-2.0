import { View, Text, Pressable, StyleSheet } from "react-native";
import { T, statusColor } from "../theme.js";

export function PlayerCard({ player, game, mode, sport }) {
  const sc = statusColor(game.status);
  const confidencePct = Math.min(100, player.confidence);

  return (
    <View style={s.column}>
      <View style={s.sectionLabel}>
        <Text style={s.sectionLabelLeft}>FOCUS</Text>
        <Text style={s.sectionLabelRight}>
          {mode === "live" ? "Updated after state change" : "Prepared view"}
        </Text>
      </View>

      <View style={s.heroCard}>
        <View style={s.cardHead}>
          <View style={s.playerIdRow}>
            <View style={s.athleteVisual}>
              <Text style={s.visualLabel}>{sport.toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.playerName}>{player.name}</Text>
              <Text style={s.playerMeta}>{player.role} · {player.team} · vs {player.opponent}</Text>
            </View>
          </View>
          <View style={{ flexDirection: "row", gap: 7 }}>
            <Pressable style={s.quietButton}><Text style={s.quietButtonText}>Pin</Text></Pressable>
            <Pressable style={s.quietButton}><Text style={s.quietButtonText}>Copy</Text></Pressable>
          </View>
        </View>

        <View style={s.heroStat}>
          <Text style={s.heroStatLabel}>Current view · {player.window}</Text>
          <Text style={s.heroStatValue}>
            {player.projection} <Text style={s.heroStatValueSmall}>vs {player.line}</Text>
          </Text>
          <View style={s.barLine}>
            <View style={[s.barFill, { width: `${confidencePct}%` }]} />
          </View>
          <View style={s.rowSpread}>
            <Text style={s.smallNote}>Probability {player.probability}</Text>
            <View style={[s.status, { borderColor: sc.border, backgroundColor: sc.bg }]}>
              <Text style={[s.statusText, { color: sc.fg }]}>{game.status.toUpperCase()}</Text>
            </View>
          </View>
        </View>

        <View style={s.metricGrid}>
          <View style={s.metric}>
            <Text style={s.metricLabel}>DIFFERENCE</Text>
            <Text style={[s.metricValue, { color: T.accent }]}>{player.edge}</Text>
          </View>
          <View style={s.metric}>
            <Text style={s.metricLabel}>CONFIDENCE</Text>
            <Text style={s.metricValue}>{player.confidence}%</Text>
          </View>
          <View style={s.metric}>
            <Text style={s.metricLabel}>FORM</Text>
            <Text style={[s.metricValue, { color: T.warn }]}>{player.form}</Text>
          </View>
        </View>

        <View style={s.modelBar}>
          <View style={s.rowSpread}>
            <Text style={s.metricLabel}>MODEL VIEW</Text>
            <Text style={s.smallNote}>{player.model}</Text>
          </View>
          <Text style={[s.smallNote, { marginTop: 10 }]}>{player.note}</Text>
        </View>

        <View style={s.cardFoot}>
          <Text style={s.footText}>Source · {player.source}</Text>
          <Text style={s.footText}>Updated {player.updated}</Text>
        </View>
      </View>

      <View style={s.lowerGrid}>
        <View style={[s.tablePanel, { flex: 1.15 }]}>
          <View style={s.sectionLabel}>
            <Text style={s.sectionLabelLeft}>INPUTS</Text>
            <Text style={s.sectionLabelRight}>Current snapshot</Text>
          </View>
          {player.rows.map(([key, value]) => (
            <View key={key} style={s.tableRow}>
              <Text style={s.tableKey}>{key}</Text>
              <Text style={s.tableVal}>{value}</Text>
            </View>
          ))}
        </View>

        <View style={[s.tablePanel, { flex: 0.85 }]}>
          <View style={s.sectionLabel}>
            <Text style={s.sectionLabelLeft}>STATE</Text>
            <Text style={s.sectionLabelRight}>{mode}</Text>
          </View>
          <View style={s.tableRow}>
            <Text style={s.tableKey}>Game</Text>
            <Text style={s.tableVal}>{game.away} · {game.home}</Text>
          </View>
          <View style={s.tableRow}>
            <Text style={s.tableKey}>Period</Text>
            <Text style={s.tableVal}>{game.period}</Text>
          </View>
          <View style={s.tableRow}>
            <Text style={s.tableKey}>Valid until</Text>
            <Text style={s.tableVal}>New update</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  column: { paddingHorizontal: 20, marginTop: 18 },
  sectionLabel: { flexDirection: "row", justifyContent: "space-between", marginBottom: 10 },
  sectionLabelLeft: { color: T.muted, letterSpacing: 1.3, textTransform: "uppercase", fontSize: 10, fontWeight: "700" },
  sectionLabelRight: { color: T.faint, fontSize: 11 },
  heroCard: {
    backgroundColor: T.panel, borderWidth: 1, borderColor: "#202a30",
    borderRadius: T.radius, padding: 18,
  },
  cardHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  playerIdRow: { flexDirection: "row", alignItems: "center", gap: 12, flex: 1 },
  athleteVisual: {
    width: 62, height: 62, borderRadius: 12, borderWidth: 1, borderColor: "#45655a",
    backgroundColor: "#304841", alignItems: "center", justifyContent: "flex-end", padding: 4,
  },
  visualLabel: {
    color: T.muted, fontSize: 8, letterSpacing: 0.8,
    backgroundColor: "#202a31", borderWidth: 1, borderColor: T.line,
    paddingHorizontal: 4, paddingVertical: 1, borderRadius: 4,
  },
  playerName: { color: T.text, fontSize: 18, fontWeight: "700", letterSpacing: -0.5 },
  playerMeta: { color: T.muted, fontSize: 12, marginTop: 4 },
  quietButton: {
    borderWidth: 1, borderColor: T.line, borderRadius: 8,
    paddingHorizontal: 10, paddingVertical: 6,
  },
  quietButtonText: { color: T.muted, fontSize: 11 },
  heroStat: {
    marginTop: 18, padding: 15, borderRadius: 12,
    backgroundColor: T.panel2, borderWidth: 1, borderColor: "#202a30",
  },
  heroStatLabel: { color: T.muted, fontSize: 10, fontWeight: "700", letterSpacing: 0.6, textTransform: "uppercase" },
  heroStatValue: { color: T.text, fontSize: 30, letterSpacing: -1.5, marginTop: 6, fontWeight: "700" },
  heroStatValueSmall: { color: T.muted, fontSize: 13, fontWeight: "400" },
  barLine: { height: 7, borderRadius: 20, backgroundColor: "#273039", overflow: "hidden", marginTop: 10, marginBottom: 7 },
  barFill: { height: "100%", backgroundColor: T.accent, borderRadius: 20 },
  rowSpread: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  smallNote: { color: T.muted, fontSize: 12, lineHeight: 18 },
  status: { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 20, borderWidth: 1 },
  statusText: { fontSize: 10, letterSpacing: 0.8 },
  metricGrid: { flexDirection: "row", gap: 8, marginTop: 12 },
  metric: {
    flex: 1, padding: 10, borderWidth: 1, borderColor: "#202a30", borderRadius: 10,
  },
  metricLabel: { color: T.faint, fontSize: 9, letterSpacing: 0.8, fontWeight: "700" },
  metricValue: { color: T.text, fontSize: 16, marginTop: 6, fontWeight: "700" },
  modelBar: {
    paddingTop: 12, marginTop: 14, borderTopWidth: 1, borderTopColor: "#202a30",
  },
  cardFoot: {
    flexDirection: "row", justifyContent: "space-between",
    paddingTop: 14, marginTop: 14, borderTopWidth: 1, borderTopColor: "#202a30",
  },
  footText: { color: T.faint, fontSize: 10 },
  lowerGrid: { flexDirection: "row", gap: 12, marginTop: 14 },
  tablePanel: {
    backgroundColor: T.panel, borderWidth: 1, borderColor: "#202a30",
    borderRadius: T.radius, padding: 14,
  },
  tableRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#202a30",
  },
  tableKey: { color: T.muted, fontSize: 12 },
  tableVal: { color: T.text, fontSize: 12, fontWeight: "700" },
});
