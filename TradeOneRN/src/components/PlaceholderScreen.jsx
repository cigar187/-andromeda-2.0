// PlaceholderScreen — reusable "coming soon" screen for BUILD / HISTORY / SETTINGS tabs.
// Sizes to fill available space, centers a small tile with title + subtitle.
import { View, Text, StyleSheet } from "react-native";
import { M31Colors } from "../theme/m31.js";

export function PlaceholderScreen({ title, subtitle }) {
  return (
    <View style={s.wrap}>
      <View style={s.tile}>
        <Text style={s.kick}>{title}</Text>
        <Text style={s.body}>
          {subtitle || "Coming soon — this tab drops in as a module, no app update needed."}
        </Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: M31Colors.bg, alignItems: "center", justifyContent: "center", padding: 20 },
  tile: {
    borderWidth: 1, borderStyle: "dashed", borderColor: M31Colors.addonDashed,
    borderRadius: 18, padding: 28, alignItems: "center", maxWidth: 360,
  },
  kick: { fontSize: 18, fontWeight: "800", letterSpacing: 2.16, color: M31Colors.ink },
  body: { marginTop: 10, fontSize: 13, color: M31Colors.ink3, textAlign: "center", lineHeight: 20 },
});
