import json
import math
import os
import re
import urllib.request
from collections import Counter

import boto3

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
DEFAULT_BUCKET = os.environ.get("DATA_BUCKET")
TEXT_MODEL_ID = os.environ.get("TEXT_MODEL_ID", "google.gemma-3-4b-it")
MANTLE_BASE_URL = os.environ.get("MANTLE_BASE_URL", "https://bedrock-mantle.us-east-1.api.aws/v1")
BEDROCK_KEY_PARAM = os.environ.get("BEDROCK_KEY_PARAM")

_cached_key = None

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "of", "to", "in", "on", "for", "with",
    "this", "that", "these", "those", "it", "its", "as", "by", "at",
    "from", "into", "about", "also", "which", "what", "how", "where",
}


class ThrottlingException(Exception):
    pass


def api_key():
    global _cached_key
    if _cached_key is None:
        resp = ssm.get_parameter(Name=BEDROCK_KEY_PARAM, WithDecryption=True)
        _cached_key = resp["Parameter"]["Value"]
    return _cached_key


def tokenize(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def tfidf_search(index_doc, query, top_n=3):
    chunks = index_doc["chunks"]
    n_chunks = len(chunks)
    query_terms = tokenize(query)
    if not query_terms or n_chunks == 0:
        return []

    doc_freq = Counter()
    for chunk in chunks:
        for term in set(chunk["tf"].keys()) & set(query_terms):
            doc_freq[term] += 1

    scores = []
    for chunk in chunks:
        score = 0.0
        for term in query_terms:
            tf = chunk["tf"].get(term, 0)
            if tf == 0:
                continue
            idf = math.log((n_chunks + 1) / (1 + doc_freq.get(term, 0))) + 1
            score += tf * idf
        scores.append((chunk, score))

    scores.sort(key=lambda x: -x[1])
    return [c for c, s in scores[:top_n] if s > 0]


def make_label(chunk):
    if chunk.get("startSec") is not None:
        start = int(chunk["startSec"])
        end = int(chunk["endSec"])
        return f"{start // 60}:{start % 60:02d}-{end // 60}:{end % 60:02d}"
    if chunk.get("pageStart") is not None:
        p1, p2 = chunk["pageStart"], chunk["pageEnd"]
        return f"p.{p1}" if p1 == p2 else f"pp.{p1}-{p2}"
    return ""


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


def answer_question(index_doc, question, top_n=3, max_tokens=200):
    top_chunks = tfidf_search(index_doc, question, top_n=top_n)
    context = "\n\n".join(c["text"] for c in top_chunks)

    instruction = (
        "Answer the question using only the context below. "
        "If the answer is not in the context, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    answer_text = generate(instruction, "", max_tokens=max_tokens)

    citations = [
        {
            "documentId": index_doc["documentId"],
            "fileName": index_doc.get("fileName", ""),
            "label": make_label(c),
            "snippet": c["text"][:200],
        }
        for c in top_chunks
    ]
    return {"answer": answer_text, "citations": citations}


def parse_request(event):
    """Support both direct invoke (dict) and API Gateway proxy (event body as JSON string)."""
    if "body" in event:
        body = event["body"]
        payload = json.loads(body) if isinstance(body, str) else body
    else:
        payload = event
    return payload.get("question"), payload.get("documentId")


def lambda_handler(event, context):
    user_id = event.get("userId") or (event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {}).get("sub"))
    question, document_id = parse_request(event)

    if not question:
        return {"error": "question is required"}
    if not document_id:
        return {"error": "documentId is required"}

    bucket = event.get("bucket", DEFAULT_BUCKET)
    index_key = f"processed/{user_id}/{document_id}/index.json"

    obj = s3.get_object(Bucket=bucket, Key=index_key)
    index_doc = json.loads(obj["Body"].read())

    return answer_question(index_doc, question)
