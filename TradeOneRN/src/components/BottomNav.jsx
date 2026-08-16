// BottomNav — 5-tab persistent bottom nav (matches the M31 mock at design/andromeda-mock.html)
// Uses unicode/emoji glyphs to avoid pulling in @expo/vector-icons.
import { View, Text, Pressable, StyleSheet } from "react-native";
import { M31Colors } from "../theme/m31.js";

// Tab id → { label, glyph }. Keep in sync with App.js's tab state.
export const TABS = [
  { id: "home",      label: "HOME",      glyph: "✦" },
  { id: "andromeda", label: "ANDROMEDA", glyph: "◆" },
  { id: "build",     label: "BUILD",     glyph: "▤" },
  { id: "history",   label: "HISTORY",   glyph: "↻" },
  { id: "settings",  label: "SETTINGS",  glyph: "⚙" },
];

export function BottomNav({ active, onSelect }) {
  return (
    <View style={s.nav}>
      {TABS.map((t) => {
        const on = t.id === active;
        return (
          <Pressable
            key={t.id}
            onPress={() => onSelect(t.id)}
            style={s.tab}
            hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
          >
            <Text style={[s.glyph, on && s.glyphOn]}>{t.glyph}</Text>
            <Text style={[s.label, on && s.labelOn]}>{t.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  nav: {
    height: 72,
    borderTopWidth: 1,
    borderTopColor: M31Colors.line,
    backgroundColor: M31Colors.bg,
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "center",
    paddingBottom: 12,
    paddingTop: 6,
    paddingHorizontal: 8,
  },
  tab: { alignItems: "center", gap: 4, paddingHorizontal: 4 },
  glyph: { fontSize: 15, fontWeight: "800", color: M31Colors.ink3 },
  glyphOn: { color: M31Colors.cyan, textShadowColor: M31Colors.cyanA60 || "rgba(0,229,255,0.6)", textShadowRadius: 6 },
  label: { fontSize: 9, letterSpacing: 0.5, color: M31Colors.ink3, fontWeight: "800" },
  labelOn: { color: M31Colors.cyan },
});
