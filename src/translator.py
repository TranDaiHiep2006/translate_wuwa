"""Offline translation engines.

One common interface hides the engine behind ``translate(texts) -> texts``:

* :class:`ArgosEngine` - Argos Translate with the ``translate-en_vi`` package
  (CTranslate2 / OpenNMT).
* :class:`MarianEngine` - Helsinki-NLP ``opus-mt-en-vi`` (MarianMT) through
  transformers, preferring a CTranslate2 build when one is available.

No engine ever calls an online API: everything runs locally.
"""

from __future__ import annotations

import re
import time
from typing import List, Sequence

# The 10 English game-style sentences used to benchmark both engines.
SAMPLE_SENTENCES: List[str] = [
    "Rover, the Tacet Field is spreading across the northern plains.",
    "Resonators are the only ones who can enter the Tacet Discord.",
    "You have obtained a new Waveplate for your Rover.",
    "The Tacet Mark on your shoulder is resonating with the Inferno attribute.",
    "Complete the quest to reach the Storm City before the storm arrives.",
    "Your attack power increases by 15% when the Havoc attribute is active.",
    "The Shorekeeper has granted you a blessing for the next expedition.",
    "Head to the supply station to exchange your tokens for rare materials.",
    "Jiyan will join your party and unlock the gliding skill.",
    "The Echo has been recorded. Replay it to learn more about the Tacet Discord.",
]

_PLACEHOLDER_RE = re.compile(r"[^A-Za-z]*GLOSSARY\d+[^A-Za-z]*")


class TranslationError(RuntimeError):
    """Raised when a translation engine cannot be used."""


class BaseEngine:
    """Common interface of every translation engine."""

    name = "base"

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self._ready = False

    def load(self) -> None:
        """Load the model. Called lazily on the first translation."""
        raise NotImplementedError

    def translate(self, texts: Sequence[str]) -> List[str]:
        """Translate a list of English sentences into Vietnamese."""
        raise NotImplementedError

    def translate_one(self, text: str) -> str:
        """Translate a single sentence."""
        return self.translate([text])[0]

    def warmup(self) -> float:
        """Load the model and translate a dummy sentence. Returns elapsed ms."""
        start = time.perf_counter()
        self.translate(["Hello."])
        return (time.perf_counter() - start) * 1000.0

    @property
    def ready(self) -> bool:
        return self._ready


class ArgosEngine(BaseEngine):
    """Argos Translate engine (``translate-en_vi`` package)."""

    name = "argos"

    def load(self) -> None:
        if self._ready:
            return
        try:
            import argostranslate.package  # type: ignore  # noqa: F401
            import argostranslate.translate  # type: ignore
        except Exception as exc:
            raise TranslationError(f"argostranslate is not installed: {exc}") from exc

        # Stanza must not try to reach GitHub for the resources.json.
        from .offline import patch_stanza_offline

        patch_stanza_offline()

        installed = argostranslate.translate.get_installed_languages()
        source = next((l for l in installed if l.code == "en"), None)
        target = next((l for l in installed if l.code == "vi"), None)
        if source is None or target is None:
            try:
                argostranslate.package.update_package_index()
                installed = argostranslate.translate.get_installed_languages()
                source = next((l for l in installed if l.code == "en"), None)
                target = next((l for l in installed if l.code == "vi"), None)
            except Exception as exc:
                raise TranslationError(
                    f"could not refresh the Argos package index: {exc}"
                ) from exc
        if source is None or target is None:
            raise TranslationError(
                "the Argos package translate-en_vi is not installed. "
                "Install it once (needs internet) with: "
                "python -c \"import argostranslate.package as p; p.update_package_index(); "
                "p.install_from_path(lambda x: x.name=='translate-en_vi' and x.value, "
                "install_package=True)\""
            )
        self._source = source
        self._target = target
        self._translation = source.get_translation(target)
        if self._translation is None:
            raise TranslationError(
                "Argos has no en->vi translation model installed."
            )
        self._ready = True

    def translate(self, texts: Sequence[str]) -> List[str]:
        self.load()

        results: List[str] = []
        for text in texts:
            if not text.strip():
                results.append("")
                continue
            try:
                results.append(self._translation.translate(text))
            except Exception as exc:  # pragma: no cover - defensive
                raise TranslationError(f"Argos translation failed: {exc}") from exc
        return results


class MarianEngine(BaseEngine):
    """Helsinki-NLP ``opus-mt-en-vi`` (MarianMT) engine via transformers."""

    name = "marian"

    MODEL_HF = "Helsinki-NLP/opus-mt-en-vi"

    def __init__(self, device: str = "cpu") -> None:
        super().__init__(device)
        self._translator = None
        self._tokenizer = None
        self._backend = ""

    def load(self) -> None:
        if self._ready:
            return
        try:
            import torch  # noqa: F401
            from transformers import MarianMTModel, MarianTokenizer
        except Exception as exc:
            raise TranslationError(f"transformers/torch are not installed: {exc}") from exc

        try:
            import tempfile

            import ctranslate2  # type: ignore
            from ctranslate2.converters import TransformersConverter  # type: ignore

            with tempfile.TemporaryDirectory() as tmp:
                converter = TransformersConverter(self.MODEL_HF, copy_files=False)
                converter.convert(tmp, quantization="int8")
                self._translator = ctranslate2.Translator(
                    tmp, device=self.device, inter_threads=1, intra_threads=2
                )
            self._backend = "ctranslate2-int8"
            self._ready = True
            return
        except Exception:
            # Fall back to plain transformers (slower but works).
            pass

        try:
            self._tokenizer = MarianTokenizer.from_pretrained(self.MODEL_HF)
            self._translator = MarianMTModel.from_pretrained(self.MODEL_HF)
            self._translator.eval()
            self._backend = "transformers"
            self._ready = True
        except Exception as exc:
            raise TranslationError(
                f"could not load the opus-mt-en-vi model: {exc}"
            ) from exc

    def translate(self, texts: Sequence[str]) -> List[str]:
        self.load()
        import torch

        results: List[str] = []
        if self._backend == "ctranslate2-int8":
            source = [t.replace("\n", " ") for t in texts]
            out = self._translator.translate_batch(
                source, beam_size=1, max_batch_size=8
            )
            for item in out:
                results.append(item.hypotheses[0].strip())
            return results

        for text in texts:
            batch = self._tokenizer([text], return_tensors="pt", padding=True)
            with torch.no_grad():
                generated = self._translator.generate(**batch, max_new_tokens=256)
            results.append(
                self._tokenizer.decode(generated[0], skip_special_tokens=True).strip()
            )
        return results


def create_engine(name: str = "argos", device: str = "cpu") -> BaseEngine:
    """Create a translation engine by name."""
    name = (name or "").lower()
    if name == "argos":
        return ArgosEngine(device=device)
    if name in ("marian", "mariamt", "opus-mt", "helsinki"):
        return MarianEngine(device=device)
    raise TranslationError(f"unknown translation engine: {name!r}")


def benchmark_engines(
    names: Sequence[str] = ("argos", "marian"),
    sentences: Sequence[str] = tuple(SAMPLE_SENTENCES),
    device: str = "cpu",
) -> List[dict]:
    """Benchmark the engines on the same sentences.

    Returns one dict per engine with the name, whether it worked, the average
    latency per sentence in milliseconds, the individual outputs and the error
    message when it failed.
    """
    results: List[dict] = []
    for name in names:
        entry: dict = {
            "engine": name,
            "ok": False,
            "avg_ms": float("nan"),
            "outputs": [],
            "error": "",
        }
        try:
            engine = create_engine(name, device=device)
            engine.load()
            start = time.perf_counter()
            outputs = engine.translate(list(sentences))
            elapsed = (time.perf_counter() - start) * 1000.0
            entry["ok"] = True
            entry["avg_ms"] = round(elapsed / max(1, len(sentences)), 2)
            entry["total_ms"] = round(elapsed, 2)
            entry["outputs"] = outputs
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)
    return results
