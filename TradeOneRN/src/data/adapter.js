import { catalog, news, sports } from "./mockData.js";

export function createDataAdapter({ fetcher = null, demo = true } = {}) {
  async function read(path, demoValue) {
    if (!fetcher) {
      if (demo) return demoValue;
      throw new Error(`No data adapter is configured for ${path}`);
    }
    const value = await fetcher(path);
    if (value == null) throw new Error(`Data adapter returned no data for ${path}`);
    return value;
  }
  return {
    sports,
    async getSlate(sport, mode) {
      if (!catalog[sport]) throw new Error(`No demo data for sport ${sport}`);
      return read(`/v1/slate?sport=${encodeURIComponent(sport)}&mode=${mode}`, catalog[sport]);
    },
    getNews: (sport, mode) => read(`/v1/feed?sport=${encodeURIComponent(sport)}&mode=${mode}`, news),
    async getActive(sport, gameId, mode) {
      const slate = await this.getSlate(sport, mode);
      const game = slate.games.find((item) => item.id === gameId);
      if (!game) throw new Error(`No game ${gameId} exists in the ${sport} slate`);
      const player = slate.players[game.id];
      if (!player) throw new Error(`No player view exists for game ${game.id}`);
      return { game, player };
    }
  };
}
