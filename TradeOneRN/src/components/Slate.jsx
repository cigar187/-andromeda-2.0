import { View, Text, Pressable, StyleSheet } from "react-native";
import { T, statusColor } from "../theme.js";

export function Slate({ games, activeId, onSelect }) {
  return (
    <View style={s.column}>
      <View style={s.sectionLabel}>
        <Text style={s.sectionLabelLeft}>SLATE</Text>
        <Text style={s.sectionLabelRight}>{games.length} tracked</Text>
      </View>
      <View style={{ gap: 8 }}>
        {games.map((game) => {
          const selected = game.id === activeId;
          const sc = statusColor(game.status);
          return (
            <Pressable key={game.id} onPress={() => onSelect(game.id)}
              style={[s.gameRow, selected && s.gameRowSelected]}>
              <View style={s.rowSpread}>
                <Text style={s.gameRowTopText}>{game.league}</Text>
                <Text style={s.gameRowTopText}>{game.time}</Text>
              </View>
              <View style={{ marginVertical: 10, gap: 2 }}>
                <Text style={s.matchupAway}>{game.away}</Text>
                <Text style={s.matchupHome}>{game.home}</Text>
              </View>
              <View style={s.rowSpread}>
                <Text style={s.gameRowBottomText}>{game.period}</Text>
                <View style={[s.status, { borderColor: sc.border, backgroundColor: sc.bg }]}>
                  <Text style={[s.statusText, { color: sc.fg }]}>{game.status.toUpperCase()}</Text>
                </View>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  column: { paddingHorizontal: 20, marginTop: 14 },
  sectionLabel: { flexDirection: "row", justifyContent: "space-between", marginBottom: 10 },
  sectionLabelLeft: { color: T.muted, letterSpacing: 1.3, textTransform: "uppercase", fontSize: 10, fontWeight: "700" },
  sectionLabelRight: { color: T.faint, fontSize: 11 },
  gameRow: {
    borderWidth: 1, borderColor: "#202a30", backgroundColor: T.panel,
    padding: 13, borderRadius: 11,
  },
  gameRowSelected: { borderColor: "#476057", backgroundColor: T.panel2 },
  rowSpread: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  gameRowTopText: { color: T.faint, fontSize: 10, textTransform: "uppercase", letterSpacing: 0.8 },
  matchupAway: { color: T.text, fontSize: 13, fontWeight: "700" },
  matchupHome: { color: T.text, fontSize: 13 },
  gameRowBottomText: { color: T.muted, fontSize: 11 },
  status: { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 20, borderWidth: 1 },
  statusText: { fontSize: 10, letterSpacing: 0.8 },
});
