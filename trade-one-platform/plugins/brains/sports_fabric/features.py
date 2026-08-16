from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

from .contracts import CanonicalObservation, parse_time
from .text_intelligence import document_text, event_features


IDENTITY = ["sport", "league", "season", "role", "market_family", "market_stat", "team_id", "opponent_id"]


def to_frame(records: Iterable[CanonicalObservation]) -> pd.DataFrame:
    rows = []
    for record in records:
        row = {key: getattr(record, key) for key in IDENTITY}
        row.update({f"num__{key}": value for key, value in record.numeric.items()})
        row.update({f"cat__{key}": value for key, value in record.categorical.items()})
        row.update({f"inc__{key}": value for key, value in record.incumbent_predictions.items()})
        row.update({f"txtsig__{key}": value for key, value in event_features(record).items()})
        row["line"] = record.line
        row["over_odds"] = record.over_odds
        row["under_odds"] = record.under_odds
        row["hours_to_event"] = (parse_time(record.event_start) - parse_time(record.as_of)).total_seconds() / 3600
        row["as_of"] = parse_time(record.as_of)
        row["event_id"] = record.event_id
        row["participant_id"] = record.participant_id
        row["route"] = record.route
        row["text_blob"] = document_text(record)
        row["target"] = record.labels.get("over_hit")
        row["actual_value"] = record.labels.get("actual_value")
        rows.append(row)
    return pd.DataFrame(rows).replace([math.inf, -math.inf], pd.NA)


def add_temporal_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values(["participant_id", "market_stat", "as_of"]).copy()
    groups = frame.groupby(["participant_id", "market_stat"], sort=False, dropna=False)
    for column in ["line", "over_odds"]:
        frame[f"temporal__{column}_lag1"] = groups[column].shift(1)
        frame[f"temporal__{column}_change"] = frame[column] - frame[f"temporal__{column}_lag1"]
        frame[f"temporal__{column}_ewm"] = groups[column].transform(lambda series: series.shift(1).ewm(span=5).mean())
    frame["temporal__observation_number"] = groups.cumcount()
    return frame
