// Shell — persistent chrome for Andromeda 2.0: top brand bar + children slot + bottom nav.
// Sport strip is NOT here anymore — it lives inside AndromedaFeed (only relevant on that tab).
import { View, Text, StyleSheet } from "react-native";
import { M31Colors } from "../theme/m31.js";
import { BottomNav } from "./BottomNav.jsx";

export function Shell({ activeTab, onTab, children }) {
  return (
    <View style={s.shell}>
      <View style={s.topbar}>
        <View style={s.brand}>
          <View style={s.brandMark}><Text style={s.brandMarkText}>A2</Text></View>
          <Text style={s.brandName}>ANDROMEDA 2.0</Text>
        </View>
        <View style={s.statusPill}><Text style={s.statusPillText}>Live · Pinnacle</Text></View>
      </View>

      <View style={s.body}>{children}</View>

      <BottomNav active={activeTab} onSelect={onTab} />
    </View>
  );
}

const s = StyleSheet.create({
  shell: { flex: 1, backgroundColor: M31Colors.bg },
  topbar: {
    height: 56, paddingHorizontal: 20,
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    borderBottomWidth: 1, borderBottomColor: M31Colors.line,
  },
  brand: { flexDirection: "row", alignItems: "center", gap: 11 },
  brandMark: {
    width: 28, height: 28, borderWidth: 1, borderColor: M31Colors.cyan, borderRadius: 9,
    alignItems: "center", justifyContent: "center",
  },
  brandMarkText: { color: M31Colors.cyan, fontSize: 13, fontWeight: "800" },
  brandName: { fontSize: 14, letterSpacing: 1.6, color: M31Colors.ink, fontWeight: "700" },
  statusPill: {
    paddingHorizontal: 9, paddingVertical: 4, borderRadius: 20, borderWidth: 1,
    borderColor: M31Colors.driverBorder, backgroundColor: M31Colors.driverA10,
  },
  statusPillText: { color: M31Colors.cyan, fontSize: 10, letterSpacing: 0.6, fontWeight: "800" },
  body: { flex: 1 },
});
