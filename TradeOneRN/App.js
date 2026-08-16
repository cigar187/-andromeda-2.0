import { useState } from "react";
import { StatusBar } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { Shell } from "./src/components/Shell.jsx";
import { Home } from "./src/components/Home.jsx";
import { AndromedaFeed } from "./src/components/AndromedaFeed.jsx";
import { PlaceholderScreen } from "./src/components/PlaceholderScreen.jsx";
import { M31Colors } from "./src/theme/m31.js";

export default function App() {
  const [tab, setTab] = useState("home");
  const [sport, setSport] = useState("Baseball");

  return (
    <SafeAreaProvider>
      <StatusBar barStyle="light-content" backgroundColor={M31Colors.bg} />
      <SafeAreaView style={{ flex: 1, backgroundColor: M31Colors.bg }} edges={["top"]}>
        <Shell activeTab={tab} onTab={setTab}>
          {tab === "home" && <Home onEnterFeed={() => setTab("andromeda")} />}
          {tab === "andromeda" && (
            <AndromedaFeed sport={sport} onSport={setSport} />
          )}
          {tab === "build" && (
            <PlaceholderScreen title="BUILD" subtitle="Deck builder + parlay assembly — coming soon. Drops in as a module, no app update needed." />
          )}
          {tab === "history" && (
            <PlaceholderScreen title="HISTORY" subtitle="Slate history, verdict outcomes, grade rollups — wires in when the grader is live." />
          )}
          {tab === "settings" && (
            <PlaceholderScreen title="SETTINGS" subtitle="Preferences, endpoint config, alerts — coming soon." />
          )}
        </Shell>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
