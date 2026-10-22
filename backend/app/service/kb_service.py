import json
from pathlib import Path

import numpy as np

from app.config import BASE_DIR

KB_DIR = BASE_DIR / "data" / "kb"
INDEX_FILE = BASE_DIR / "data" / "kb_index.json"

_model = None
_docs: list[dict] | None = None
_vectors: np.ndarray | None = None


def get_model():
    """懒加载中文向量模型：只加载一次，之后复用同一个实例"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    return _model


def _read_docs() -> list[dict]:
    KB_DIR.mkdir(parents=True, exist_ok=True)
    docs = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            docs.append({"id": path.stem, "source": path.name, "content": text})
    return docs


def _encode(texts: list[str]) -> np.ndarray:
    vectors = get_model().encode(texts, normalize_embeddings=True)
    return np.asarray(vectors, dtype="float32")


def _load_index(docs: list[dict]) -> np.ndarray | None:
    """读取磁盘缓存，文档内容或数量变化时返回 None 触发重建"""
    if not INDEX_FILE.exists():
        return None
    try:
        raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        if [item["id"] for item in raw.get("docs", [])] != [item["id"] for item in docs]:
            return None
        if [item["content"] for item in raw.get("docs", [])] != [item["content"] for item in docs]:
            return None
        vectors = np.asarray(raw.get("vectors", []), dtype="float32")
        if vectors.shape[0] != len(docs):
            return None
        return vectors
    except Exception:
        return None


def _save_index(docs: list[dict], vectors: np.ndarray):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"docs": docs, "vectors": vectors.tolist()}
    INDEX_FILE.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _ensure_index():
    global _docs, _vectors
    if _docs is not None and _vectors is not None:
        return
    docs = _read_docs()
    vectors = _load_index(docs)
    if vectors is None:
        vectors = _encode([item["content"] for item in docs]) if docs else np.zeros((0, 512), dtype="float32")
        _save_index(docs, vectors)
    _docs = docs
    _vectors = vectors


def search(query: str):
    """根据关键字检索知识库，返回最相关的 2 段内容"""
    _ensure_index()
    if not _docs or _vectors is None or len(_docs) == 0:
        return ""
    query_vector = _encode([query])[0]
    scores = _vectors @ query_vector  # 向量已归一化，点积即余弦相似度
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    parts = []
    for index, score in ranked[:2]:
        if float(score) < 0.5:
            continue
        item = _docs[index]
        parts.append(f"[{item['source']}]\n{item['content']}")
    return "\n\n".join(parts)


def warmup():
    """启动时预热：把模型加载 + 首次检索的开销付在启动阶段"""
    _ensure_index()
    if _docs:
        search("开放时间")
