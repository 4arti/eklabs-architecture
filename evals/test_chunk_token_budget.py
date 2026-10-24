"""Eval: real chunks never exceed BGE's 512-token limit once fully
contextualized (spec §6: a citable chunk has to actually embed correctly,
not get silently truncated). Uses real EPAR PDFs from evals/manifest.yaml,
not synthetic text — this is exactly the kind of heavy, real-model,
real-corpus check that belongs in evals/, not the fast src/*/tests/ suite
(loads the actual ~1.3GB BGE model and runs real Docling parsing).

A sample of 3 EPARs, not all of them — this guards the token-budget
invariant (ingestion/chunking.py's _MAX_TOKENS margin), not full-corpus OCR
accuracy; that's a separate, bigger eval still to be written.
"""

from pathlib import Path

import yaml
from transformers import AutoTokenizer

from eklabs_platform.ingestion.chunking import chunk_document
from eklabs_platform.ingestion.parsing import parse_document
from eklabs_platform.knowledge.embedding import MODEL_NAME

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_PATH = _REPO_ROOT / "evals" / "manifest.yaml"
_SAMPLE_SIZE = 3
# BGE-large-en-v1.5's real limit; chunking.py budgets for 440 with margin.
_BGE_TOKEN_LIMIT = 512


def _sample_epar_paths() -> list[Path]:
    manifest = yaml.safe_load(_MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = [e for e in manifest["entries"] if "ocr" in e.get("capability", [])]
    return [_REPO_ROOT / "evals" / e["path"] for e in entries[:_SAMPLE_SIZE]]


async def test_real_epar_chunks_stay_under_bge_token_limit() -> None:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    for pdf_path in _sample_epar_paths():
        assert pdf_path.exists(), f"missing fixture: {pdf_path} — run scripts/fetch_sources.py"
        parsed = await parse_document(pdf_path.name, pdf_path.read_bytes())
        chunks = await chunk_document(parsed.docling_doc)
        assert chunks, f"{pdf_path.name} produced zero chunks"

        for chunk in chunks:
            token_count = len(tokenizer.tokenize(chunk.text))
            assert token_count <= _BGE_TOKEN_LIMIT, (
                f"{pdf_path.name}: chunk exceeds BGE's {_BGE_TOKEN_LIMIT}-token limit "
                f"({token_count} tokens) — chunking.py's _MAX_TOKENS margin is no longer "
                f"enough: {chunk.text[:120]!r}..."
            )
