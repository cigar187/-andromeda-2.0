from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?|[^\w\s]")


class SportsTokenizer:
    """Owned word-piece-lite tokenizer trained only on supplied sports text."""

    SPECIAL = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"]

    def __init__(self, vocabulary: dict[str, int] | None = None, max_length: int = 192) -> None:
        self.vocabulary = vocabulary or {token: index for index, token in enumerate(self.SPECIAL)}
        self.max_length = max_length

    def fit(self, documents: list[str], vocabulary_size: int = 32000, min_frequency: int = 2) -> "SportsTokenizer":
        counts: Counter[str] = Counter()
        for document in documents:
            tokens = [token.lower() for token in TOKEN_PATTERN.findall(document)]
            counts.update(tokens)
            for token in tokens:
                if len(token) > 4:
                    counts.update(f"##{token[index:index + 3]}" for index in range(len(token) - 2))
        selected = [token for token, count in counts.most_common() if count >= min_frequency]
        selected = selected[: max(0, vocabulary_size - len(self.SPECIAL))]
        self.vocabulary = {token: index for index, token in enumerate(self.SPECIAL + selected)}
        return self

    def encode(self, text: str) -> tuple[list[int], list[int]]:
        unknown = self.vocabulary["[UNK]"]
        ids = [self.vocabulary["[CLS]"]]
        for raw in TOKEN_PATTERN.findall(text):
            token = raw.lower()
            if token in self.vocabulary:
                ids.append(self.vocabulary[token])
            elif len(token) > 4:
                pieces = [self.vocabulary.get(f"##{token[index:index + 3]}", unknown) for index in range(len(token) - 2)]
                ids.extend(pieces)
            else:
                ids.append(unknown)
            if len(ids) >= self.max_length - 1:
                break
        ids.append(self.vocabulary["[SEP]"])
        mask = [1] * len(ids)
        padding = self.max_length - len(ids)
        return ids + [self.vocabulary["[PAD]"]] * padding, mask + [0] * padding

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"vocabulary": self.vocabulary, "max_length": self.max_length}, sort_keys=True))

    @classmethod
    def load(cls, path: str | Path) -> "SportsTokenizer":
        payload = json.loads(Path(path).read_text())
        return cls(payload["vocabulary"], int(payload["max_length"]))

    def __len__(self) -> int:
        return len(self.vocabulary)
