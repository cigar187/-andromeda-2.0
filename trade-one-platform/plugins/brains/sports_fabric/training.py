from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class InsufficientTrainingData(Exception):
    """A trainer refused to fit because the labeled sample was too small to
    produce a real model. Rule-4: never return an empty-shaped model that
    downstream code will treat as trained. The caller decides whether to
    defer, retry after more data lands, or abort the training run.
    """

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .contracts import CanonicalObservation
from .features import add_temporal_features, to_frame


@dataclass
class ModelBundle:
    experts: dict[str, object]
    meta_model: object
    quantile_models: dict[str, object]
    feature_columns: list[str]
    text_column: str
    expert_order: list[str]
    metrics: dict[str, float]
    routes: list[str]
    conformal_threshold: float


class IntelligenceTrainer:
    """Leakage-aware multimodal late-fusion trainer."""

    def __init__(self, seed: int = 187) -> None:
        self.seed = seed

    def train(self, records: list[CanonicalObservation], artifact_dir: str | Path) -> ModelBundle:
        frame = add_temporal_features(to_frame(records))
        frame = frame[frame["target"].notna()].reset_index(drop=True)
        if len(frame) < 50:
            raise ValueError("at least 50 labeled point-in-time rows are required")
        frame = frame.sort_values("as_of").reset_index(drop=True)
        y = frame["target"].astype(int).to_numpy()
        groups = frame["event_id"].astype(str).to_numpy()
        builders = self._expert_builders(frame)
        folds = min(5, len(np.unique(groups)))
        if folds < 2:
            raise ValueError("training requires at least two distinct events")
        oof = np.zeros((len(frame), len(builders)))
        oof_mask = np.zeros(len(frame), dtype=bool)
        experts: dict[str, object] = {}
        for expert_index, (name, builder) in enumerate(builders.items()):
            for train_idx, valid_idx in self._chronological_splits(frame, folds):
                model = builder()
                model.fit(frame.iloc[train_idx], y[train_idx])
                oof[valid_idx, expert_index] = model.predict_proba(frame.iloc[valid_idx])[:, 1]
                oof_mask[valid_idx] = True
            final = builder()
            final.fit(frame, y)
            experts[name] = final
        meta_features = np.column_stack([oof, self._routing_matrix(frame)])
        meta = LogisticRegression(C=0.4, max_iter=3000, class_weight="balanced")
        calibrated = CalibratedClassifierCV(meta, method="isotonic", cv=3)
        calibrated.fit(meta_features[oof_mask], y[oof_mask])
        probabilities = calibrated.predict_proba(meta_features[oof_mask])[:, 1]
        scored_y = y[oof_mask]
        true_probability = np.where(scored_y == 1, probabilities, 1 - probabilities)
        conformal_threshold = float(np.quantile(1 - true_probability, 0.85, method="higher"))
        metrics = {
            "rows": float(len(frame)),
            "events": float(len(np.unique(groups))),
            "oof_rows": float(oof_mask.sum()),
            "log_loss": float(log_loss(scored_y, probabilities)),
            "brier": float(brier_score_loss(scored_y, probabilities)),
            "roc_auc": float(roc_auc_score(scored_y, probabilities)) if len(np.unique(scored_y)) > 1 else 0.5,
        }
        # Rule-4: quantile trainer raises InsufficientTrainingData when it can't
        # produce a real model. Caller must decide — here we skip quantile models
        # entirely (bundle still ships with empty quantile_models dict, which
        # downstream code MUST treat as "no floor/median/ceiling available", not
        # as "trained on zero rows").
        try:
            quantiles = self._train_quantiles(frame)
        except InsufficientTrainingData as e:
            # Explicit ERROR log so operators see quantile absence, not silent skip.
            import logging as _l
            _l.getLogger(__name__).error(
                "quantile training skipped for this bundle: %s — downstream sim tiles will be omitted", e,
            )
            quantiles = {}
        bundle = ModelBundle(
            experts=experts, meta_model=calibrated, quantile_models=quantiles,
            feature_columns=list(frame.columns), text_column="text_blob",
            expert_order=list(builders), metrics=metrics,
            routes=sorted(frame["route"].unique().tolist()),
            conformal_threshold=conformal_threshold,
        )
        artifact_dir = Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, artifact_dir / "model.joblib", compress=3)
        (artifact_dir / "manifest.json").write_text(json.dumps(metrics | {"experts": list(builders), "routes": bundle.routes}, indent=2))
        return bundle

    def _expert_builders(self, frame: pd.DataFrame) -> dict[str, Callable[[], object]]:
        numeric = [c for c in frame if c.startswith(("num__", "inc__", "txtsig__", "temporal__"))] + ["line", "over_odds", "under_odds", "hours_to_event"]
        categorical = [c for c in frame if c in {"sport", "league", "season", "role", "market_family", "market_stat", "team_id", "opponent_id"} or c.startswith("cat__")]
        preprocessor = ColumnTransformer([
            ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            ("categorical", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False, min_frequency=3))]), categorical),
        ], remainder="drop")
        builders: dict[str, Callable[[], object]] = {
            "extra_trees": lambda: Pipeline([("prep", clone(preprocessor)), ("model", ExtraTreesClassifier(n_estimators=600, min_samples_leaf=4, max_features=0.7, class_weight="balanced", n_jobs=-1, random_state=self.seed))]),
            "text": lambda: Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), analyzer="word", min_df=2, max_features=100000, sublinear_tf=True)), ("model", LogisticRegression(C=2.0, max_iter=2500, class_weight="balanced"))]),
        }
        # Text pipeline expects the Series rather than a full frame.
        builders["text"] = lambda: TextFrameClassifier()
        optional = self._optional_boosters(preprocessor)
        builders.update(optional)
        return builders

    def _optional_boosters(self, preprocessor: ColumnTransformer) -> dict[str, Callable[[], object]]:
        output: dict[str, Callable[[], object]] = {}
        try:
            from lightgbm import LGBMClassifier
            output["lightgbm"] = lambda: Pipeline([("prep", clone(preprocessor)), ("model", LGBMClassifier(n_estimators=900, learning_rate=0.035, num_leaves=31, subsample=0.85, colsample_bytree=0.8, reg_lambda=2.0, n_jobs=-1, random_state=self.seed, verbosity=-1))])
        except ImportError:
            pass
        try:
            from xgboost import XGBClassifier
            output["xgboost"] = lambda: Pipeline([("prep", clone(preprocessor)), ("model", XGBClassifier(n_estimators=800, learning_rate=0.035, max_depth=6, subsample=0.85, colsample_bytree=0.8, reg_lambda=2.0, n_jobs=-1, random_state=self.seed, eval_metric="logloss"))])
        except ImportError:
            pass
        try:
            from catboost import CatBoostClassifier
            output["catboost"] = lambda: Pipeline([("prep", clone(preprocessor)), ("model", CatBoostClassifier(iterations=900, learning_rate=0.035, depth=7, l2_leaf_reg=4.0, loss_function="Logloss", verbose=False, random_seed=self.seed, thread_count=-1))])
        except ImportError:
            pass
        return output

    @staticmethod
    def _chronological_splits(frame: pd.DataFrame, folds: int):
        event_order = (
            frame.groupby("event_id")["as_of"].min().sort_values().index.to_numpy()
        )
        blocks = [block for block in np.array_split(event_order, folds) if len(block)]
        for index in range(1, len(blocks)):
            train_events = np.concatenate(blocks[:index])
            valid_events = blocks[index]
            train_idx = np.flatnonzero(frame["event_id"].isin(train_events).to_numpy())
            valid_idx = np.flatnonzero(frame["event_id"].isin(valid_events).to_numpy())
            if len(train_idx) and len(valid_idx) and frame.iloc[train_idx]["target"].nunique() > 1:
                yield train_idx, valid_idx

    def _train_quantiles(self, frame: pd.DataFrame) -> dict[str, object]:
        labeled = frame[frame["actual_value"].notna()]
        # Rule-4: insufficient training data is a real absence, not a "training
        # succeeded with an empty model." Returning {} lets downstream code
        # believe it has a trained quantile set when it does not. Raise so the
        # caller must decide to skip or defer training.
        if len(labeled) < 30:
            raise InsufficientTrainingData(
                f"_train_quantiles: only {len(labeled)} labeled rows (need >= 30)"
            )
        columns = [c for c in frame if c.startswith(("num__", "inc__", "txtsig__", "temporal__"))] + ["line", "over_odds", "under_odds", "hours_to_event"]
        X = labeled[columns].apply(pd.to_numeric, errors="coerce").fillna(0)
        y = labeled["actual_value"].astype(float)
        models = {}
        for name, quantile in (("floor", 0.15), ("median", 0.5), ("ceiling", 0.85)):
            model = HistGradientBoostingRegressor(loss="quantile", quantile=quantile, max_iter=450, learning_rate=0.04, l2_regularization=2.0, random_state=self.seed)
            model.fit(X, y)
            models[name] = (columns, model)
        return models

    @staticmethod
    def _routing_matrix(frame: pd.DataFrame) -> np.ndarray:
        return np.column_stack([
            frame["line"].fillna(0).to_numpy(float),
            frame["hours_to_event"].fillna(0).clip(-24, 336).to_numpy(float),
            frame.filter(like="txtsig__").sum(axis=1).to_numpy(float),
            frame.filter(like="inc__").mean(axis=1).fillna(0.5).to_numpy(float),
        ])


class TextFrameClassifier:
    def __init__(self) -> None:
        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=100000, sublinear_tf=True, strip_accents="unicode")),
            ("model", LogisticRegression(C=2.0, max_iter=2500, class_weight="balanced")),
        ])

    def fit(self, frame: pd.DataFrame, y: np.ndarray):
        self.pipeline.fit(frame["text_blob"].fillna(""), y)
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict_proba(frame["text_blob"].fillna(""))
