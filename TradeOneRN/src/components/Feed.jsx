import { View, Text, StyleSheet } from "react-native";
import { T } from "../theme.js";

export function Feed({ items }) {
  return (
    <View style={s.column}>
      <View style={s.sectionLabel}>
        <Text style={s.sectionLabelLeft}>FEED</Text>
        <Text style={s.sectionLabelRight}>Latest first</Text>
      </View>
      <View style={s.feedPanel}>
        {items.map((item, i) => (
          <View key={`${item.time}-${item.tag}-${i}`}
            style={[s.feedItem, i === items.length - 1 && { borderBottomWidth: 0 }]}>
            <View style={s.feedMeta}>
              <Text style={s.tag}>{item.tag}</Text>
              <Text style={s.feedMetaTime}>{item.time}</Text>
            </View>
            <Text style={s.feedTitle}>{item.title}</Text>
            <Text style={s.feedBody}>{item.body}</Text>
            <View style={[s.feedMeta, { marginTop: 8 }]}>
              <Text style={s.feedMetaTime}>{item.source}</Text>
              <Text style={s.feedMetaTime}>Reviewed</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  column: { paddingHorizontal: 20, marginTop: 18, marginBottom: 28 },
  sectionLabel: { flexDirection: "row", justifyContent: "space-between", marginBottom: 10 },
  sectionLabelLeft: { color: T.muted, letterSpacing: 1.3, textTransform: "uppercase", fontSize: 10, fontWeight: "700" },
  sectionLabelRight: { color: T.faint, fontSize: 11 },
  feedPanel: {
    backgroundColor: T.panel, borderWidth: 1, borderColor: "#202a30",
    borderRadius: T.radius, padding: 16,
  },
  feedItem: { paddingBottom: 15, borderBottomWidth: 1, borderBottomColor: "#202a30", marginBottom: 15 },
  feedMeta: { flexDirection: "row", justifyContent: "space-between" },
  tag: { color: T.accent, fontSize: 10, fontWeight: "700", letterSpacing: 0.6 },
  feedMetaTime: { color: T.faint, fontSize: 10 },
  feedTitle: { color: T.text, fontSize: 13, marginTop: 7, marginBottom: 8, fontWeight: "700" },
  feedBody: { color: T.muted, fontSize: 11, lineHeight: 16 },
});
