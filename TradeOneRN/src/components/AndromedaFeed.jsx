// AndromedaFeed — the ANDROMEDA tab view. Hosts its own sport strip at the top
// (moved out of Shell.jsx so the sport chooser only appears when relevant).
// Fetches /api/andromeda/today?sport=<slug>, renders one AndromedaCard per verdict.
import React, { useEffect, useState, useRef } from "react";
import { View, Text, ScrollView, ActivityIndicator, Pressable, StyleSheet, RefreshControl } from "react-native";
import { AndromedaCard } from "./AndromedaCard.jsx";
import { M31Colors } from "../theme/m31.js";
import { API_BASE_URL, API_TOKEN } from "../config/api.js";

const SPORTS = ["Baseball", "Basketball", "Football", "Hockey", "Soccer"];

const SPORT_TO_SLUG = {
  Baseball: "mlb",
  Basketball: "nba",
  Football: "nfl",
  Hockey: "nhl",
  Soccer: "mls",
};

function fmtDate(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}·${m}·${day}`;
}

export function AndromedaFeed({ sport, onSport }) {
  const [cards, setCards] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [cardTypes, setCardTypes] = useState([]);
  const [activePeriod, setActivePeriod] = useState(null);
  const [activeType, setActiveType] = useState(null);
  const [slateDate, setSlateDate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchTick, setFetchTick] = useState(0);
  // Track previous sport so we can reset type/period on sport change.
  const prevSportRef = useRef(sport);
  useEffect(() => {
    if (prevSportRef.current !== sport) {
      setActiveType(null);   // will be re-picked from populated types in fetch
      setActivePeriod(null); // will be re-picked from active type's periods
      prevSportRef.current = sport;
    }
  }, [sport]);

  const onRefresh = () => {
    setRefreshing(true);
    setFetchTick((n) => n + 1);
  };

  useEffect(() => {
    const slug = SPORT_TO_SLUG[sport];
    if (!slug) {
      setCards([]);
      setLoading(false);
      setError(null);
      setRefreshing(false);
      return () => {};
    }
    let cancelled = false;
    const url = `${API_BASE_URL}/api/andromeda/today?sport=${slug}`;
    if (!refreshing) setLoading(true);
    setError(null);
    // Bearer auth on the card endpoint. Token is injected at build time via
    // EXPO_PUBLIC_ANDROMEDA_API_TOKEN (EAS secret in prod, shell env in dev).
    // Header is only sent when the token env is present — server returns 401
    // otherwise (Rule 4: no open-access fallback).
    const headers = API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {};
    fetch(url, { headers })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((body) => {
        if (cancelled) return;
        const cs = Array.isArray(body.verdicts) ? body.verdicts : [];
        const ps = Array.isArray(body.periods) ? body.periods : [];
        const ts = Array.isArray(body.card_types) ? body.card_types : [];
        setCards(cs);
        setPeriods(ps);
        setCardTypes(ts);
        // Prefer the FIRST type that actually has cards today; fall through to
        // the first defined type. Keeps operator on a populated tab by default
        // instead of landing on an empty PLAYER PROPS.
        setActiveType((prev) => {
          const populated = ts.filter((t) => (t.count || 0) > 0);
          const preferred = populated.length ? populated[0].id : (ts[0]?.id || null);
          if (prev && ts.some((t) => t.id === prev)) return prev;
          return preferred;
        });
        // activePeriod handled by the [activeType, cardTypes] useEffect below.
        setSlateDate(body.date || null);
        setLoading(false);
        setRefreshing(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e.message || e));
        setLoading(false);
        setRefreshing(false);
      });
    return () => { cancelled = true; };
  }, [sport, fetchTick]);

  const slug = SPORT_TO_SLUG[sport];
  // Type-scoped period list: read directly from the active type's `.periods`
  // (server nests them). PLAYER PROPS won't include inning periods; Football
  // won't include MLB innings.
  const activeTypeObj = cardTypes.find((t) => t.id === activeType) || null;
  const periodsForActiveType = activeTypeObj?.periods || [];
  const cardsForType = activeType ? cards.filter((c) => c.card_type === activeType) : cards;
  const cardsForPeriod = activePeriod ? cardsForType.filter((c) => c.period === activePeriod) : cardsForType;
  const normal = cardsForPeriod.filter((c) => !c.isAlert);
  const alerts = cardsForPeriod.filter((c) => c.isAlert);

  // When active type changes (or sport switches invalidates period), auto-select
  // the first period valid for the current type. If the type has no periods,
  // period stays null (period bar hides).
  useEffect(() => {
    if (!activeType || !cardTypes.length) return;
    const t = cardTypes.find((x) => x.id === activeType);
    const okPeriods = t?.periods || [];
    if (activePeriod && okPeriods.some((p) => p.id === activePeriod)) return;
    setActivePeriod(okPeriods[0]?.id || null);
  }, [activeType, cardTypes]);

  return (
    <View style={{ flex: 1, backgroundColor: M31Colors.bg }}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={s.sportStrip}
        contentContainerStyle={s.sportStripInner}
      >
        {SPORTS.map((v) => (
          <Pressable
            key={v}
            onPress={() => onSport && onSport(v)}
            style={[s.sportButton, sport === v && s.sportButtonActive]}
          >
            <Text style={[s.sportButtonText, sport === v && s.sportButtonTextActive]}>{v}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {/* Period pill strip — SCOPED to the active type. Hidden entirely when
          the type has 0 or 1 periods (no choice to make). */}
      {periodsForActiveType.length > 1 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={s.periodStrip}
          contentContainerStyle={s.periodStripInner}
        >
          {periodsForActiveType.map((p) => {
            const on = p.id === activePeriod;
            return (
              <Pressable
                key={p.id}
                onPress={() => setActivePeriod(p.id)}
                style={[s.periodPill, on && s.periodPillOn]}
              >
                <Text style={[s.periodPillText, on && s.periodPillTextOn]}>
                  {p.label}  <Text style={s.periodPillCount}>{p.count}</Text>
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      )}

      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={M31Colors.cyan}
            colors={[M31Colors.cyan]}
          />
        }
      >
      <View style={s.head}>
        <View style={{ flex: 1 }}>
          <Text style={s.headKick}>ANDROMEDA</Text>
          <Text style={s.headDate}>{(slug || sport).toUpperCase()} INTEL · {fmtDate()}</Text>
        </View>
        {cardTypes.length > 1 && (
          <View style={s.headToggle}>
            {cardTypes.map((t) => {
              const on = t.id === activeType;
              return (
                <Pressable
                  key={t.id}
                  onPress={() => setActiveType(t.id)}
                  style={[s.headToggleBtn, on && s.headToggleBtnOn]}
                >
                  <Text style={[s.headToggleTxt, on && s.headToggleTxtOn]}>
                    {t.id === "player" ? "PLAYER" : "GAME"}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        )}
      </View>

      {!slug ? (
        <View style={s.empty}>
          <Text style={s.emptyTitle}>{sport} — coming soon</Text>
          <Text style={s.emptyBody}>Only Baseball is live at launch. Other sports light up once their feeds are wired.</Text>
        </View>
      ) : loading ? (
        <View style={s.empty}>
          <ActivityIndicator color={M31Colors.cyan} />
          <Text style={[s.emptyTitle, { marginTop: 12 }]}>Loading tonight's slate…</Text>
        </View>
      ) : error ? (
        <View style={s.empty}>
          <Text style={s.emptyTitle}>Backend unreachable</Text>
          <Text style={s.emptyBody}>{error}</Text>
          <Text style={[s.emptyBody, { marginTop: 8 }]}>
            URL: {API_BASE_URL}/api/andromeda/today
          </Text>
          <Text style={[s.emptyBody, { marginTop: 8 }]}>
            Dev tip: set EXPO_PUBLIC_ANDROMEDA_API and{"\n"}EXPO_PUBLIC_ANDROMEDA_API_TOKEN before Metro.{"\n"}Prod builds inject via EAS.
          </Text>
        </View>
      ) : cards.length === 0 ? (
        <View style={s.empty}>
          <Text style={s.emptyTitle}>
            {slateDate ? `No cards for ${slateDate}` : "No slate yet"}
          </Text>
          <Text style={s.emptyBody}>
            Either there are no games today or no Pinnacle prop lines are in the bus yet.
          </Text>
        </View>
      ) : (
        <>
          {normal.map((c, i) => (
            <AndromedaCard key={c.id || `n-${i}`} card={c} initiallyOpen={i === 0} />
          ))}
          {alerts.length > 0 && (
            <>
              <Text style={s.alertLabel}>ALERT</Text>
              {alerts.map((c, i) => (
                <AndromedaCard key={c.id || `a-${i}`} card={c} initiallyOpen={false} />
              ))}
            </>
          )}
        </>
      )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  sportStrip: { borderBottomWidth: 1, borderBottomColor: M31Colors.line, height: 56, flexGrow: 0 },
  sportStripInner: { paddingHorizontal: 16, gap: 6, alignItems: "center" },
  sportButton: { paddingHorizontal: 12, paddingVertical: 16, borderBottomWidth: 2, borderBottomColor: "transparent", justifyContent: "center" },
  sportButtonActive: { borderBottomColor: M31Colors.cyan },
  sportButtonText: { color: M31Colors.ink3, fontSize: 13, fontWeight: "700" },
  sportButtonTextActive: { color: M31Colors.ink },

  typeRow: {
    flexDirection: "row", borderBottomWidth: 1, borderBottomColor: M31Colors.line,
    borderTopWidth: 1, borderTopColor: M31Colors.line,
    backgroundColor: M31Colors.surface, marginTop: 18,
  },
  typeTab: {
    flex: 1, paddingVertical: 14, alignItems: "center",
    borderBottomWidth: 3, borderBottomColor: "transparent",
  },
  typeTabOn: { borderBottomColor: M31Colors.cyan, backgroundColor: M31Colors.cyanA16 },
  typeTabText: { fontSize: 14, fontWeight: "800", letterSpacing: 1.4, color: M31Colors.ink2 },
  typeTabTextOn: { color: M31Colors.cyan },
  typeTabTextDim: { color: M31Colors.ink3, opacity: 0.55 },
  typeTabCount: { fontSize: 12, fontWeight: "700", color: M31Colors.ink3 },
  typeTabCountDim: { opacity: 0.5 },

  periodStrip: {
    borderBottomWidth: 1, borderBottomColor: M31Colors.line,
    backgroundColor: M31Colors.surface, flexGrow: 0,
  },
  periodStripInner: { paddingHorizontal: 14, paddingVertical: 12, gap: 10, alignItems: "center" },
  periodPill: {
    paddingHorizontal: 16, paddingVertical: 10, borderRadius: 999,
    borderWidth: 1, borderColor: M31Colors.line, backgroundColor: M31Colors.surface2,
    minHeight: 40, alignItems: "center", justifyContent: "center",
  },
  periodPillOn: { borderColor: M31Colors.cyan, backgroundColor: M31Colors.cyanA16 },
  periodPillDim: { opacity: 0.5, borderStyle: "dashed" },
  periodPillText: { fontSize: 14, fontWeight: "800", letterSpacing: 0.6, color: M31Colors.ink2 },
  periodPillTextOn: { color: M31Colors.cyan },
  periodPillTextDim: { color: M31Colors.ink3 },
  periodPillCount: { fontSize: 12, fontWeight: "700", color: M31Colors.ink3, letterSpacing: 0.2 },

  scroll: { paddingBottom: 40, backgroundColor: M31Colors.bg },
  head: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 4, flexDirection: "row", alignItems: "center" },
  headKick: { fontSize: 24, fontWeight: "800", letterSpacing: 2.88, color: M31Colors.ink },
  headDate: { fontSize: 12, fontWeight: "800", letterSpacing: 1.92, color: M31Colors.cyan, marginTop: 3 },
  headToggle: { flexDirection: "row", borderWidth: 1, borderColor: M31Colors.line, borderRadius: 999, overflow: "hidden" },
  headToggleBtn: { paddingHorizontal: 14, paddingVertical: 8 },
  headToggleBtnOn: { backgroundColor: M31Colors.cyanA16 },
  headToggleTxt: { fontSize: 11, fontWeight: "800", letterSpacing: 1.4, color: M31Colors.ink3 },
  headToggleTxtOn: { color: M31Colors.cyan },
  empty: {
    marginHorizontal: 16, marginTop: 40, padding: 24, borderRadius: 18,
    borderWidth: 1, borderStyle: "dashed", borderColor: M31Colors.line, alignItems: "center",
  },
  emptyTitle: { fontSize: 15, fontWeight: "800", color: M31Colors.ink2, letterSpacing: 0.3 },
  emptyBody: { marginTop: 8, fontSize: 12.5, color: M31Colors.ink3, textAlign: "center", lineHeight: 18 },
  alertLabel: {
    fontSize: 12, letterSpacing: 2.16, color: M31Colors.news, fontWeight: "800",
    marginTop: 20, marginHorizontal: 20,
  },
});
