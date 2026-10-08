import json
import os
import re
import urllib.request
from collections import defaultdict

import boto3

s3 = boto3.client("s3")
BUCKET = os.environ.get("DATA_BUCKET")
TEXT_MODEL_ID = os.environ.get("TEXT_MODEL_ID", "google.gemma-3-4b-it")
MANTLE_BASE_URL = os.environ.get("MANTLE_BASE_URL", "https://bedrock-mantle.us-east-1.api.aws/v1")

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "of", "to", "in", "on", "for", "with",
    "this", "that", "these", "those", "it", "its", "as", "by", "at",
    "from", "into", "about", "also", "which", "what", "how", "where",
}


class ThrottlingException(Exception):
    pass


def api_key():
    return os.environ["BEDROCK_API_KEY"]


def tokenize(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def search(index_doc, query, top_n=3):
    query_words = tokenize(query)
    scores = defaultdict(int)
    for word in query_words:
        for chunk_id in index_doc["index"].get(word, []):
            scores[chunk_id] += 1
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [chunk_id for chunk_id, _ in ranked[:top_n]]


def generate(instruction, text, max_tokens=200, timeout=60):
    body = {
        "model": TEXT_MODEL_ID,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": instruction + "\n\n" + text}],
    }
    req = urllib.request.Request(
        MANTLE_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429 or e.code >= 500:
            raise ThrottlingException(str(e))
        raise
    print(json.dumps({"event": "AI_USAGE", **out.get("usage", {})}))
    return out["choices"][0]["message"]["content"].strip()


def answer_question(chunks_doc, index_doc, question, top_n=3, max_tokens=200):
    chunk_ids = search(index_doc, question, top_n=top_n)
    chunks_by_id = {c["chunkId"]: c for c in chunks_doc["chunks"]}
    context_parts = [chunks_by_id[cid]["text"] for cid in chunk_ids if cid in chunks_by_id]
    context = "\n\n".join(context_parts)

    instruction = (
        "Answer the question using only the context below. "
        "If the answer isn't in the context, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    answer_text = generate(instruction, "", max_tokens=max_tokens)
    return {"question": question, "answer": answer_text, "sourceChunks": chunk_ids}


def lambda_handler(event, context):
    document_id = event["documentId"]
    question = event["question"]
    chunks_key = event.get("chunksKey", f"documents/{document_id}/chunks.json")
    index_key = event.get("indexKey", f"documents/{document_id}/index.json")

    chunks_obj = s3.get_object(Bucket=BUCKET, Key=chunks_key)
    chunks_doc = json.loads(chunks_obj["Body"].read())

    index_obj = s3.get_object(Bucket=BUCKET, Key=index_key)
    index_doc = json.loads(index_obj["Body"].read())

    result = answer_question(chunks_doc, index_doc, question)
    return {"status": "ok", **result}
