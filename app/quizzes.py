"""Source-exact course recall quizzes. No external model or invented answers."""
import re
import secrets
import random

def build_questions(pages, limit=12):
    candidates=[]
    for row in pages:
        text=row["content"]
        # Prefer complete sentences, not headers or mathematical fragments.
        sentences=re.split(r"(?<=[.!?])\s+|\n+",text)
        for sentence in sentences:
            sentence=sentence.strip()
            if not 45<=len(sentence)<=320:continue
            words=list(re.finditer(r"\b[^\W\d_]{6,24}\b",sentence,re.UNICODE))
            if not words:continue
            # Select a substantive word; the source itself is the answer key.
            word=max(words,key=lambda w:len(w.group()))
            answer=word.group()
            if len(re.findall(r"\b"+re.escape(answer)+r"\b",sentence,re.I))!=1:continue
            candidates.append({"document_id":row["document_id"],"title":row["title"],"page":row["page"],"prompt":sentence[:word.start()]+" ______ "+sentence[word.end():],"answer":answer,"excerpt":sentence})
            break
    if len(candidates)>limit:
        # Spread samples across the full indexed course, not only its first pages.
        candidates=[candidates[round(i*(len(candidates)-1)/(limit-1))] for i in range(limit)] if limit>1 else [candidates[0]]
    for q in candidates:q["id"]=secrets.token_hex(8)
    return candidates

def grade(questions,answers):
    def normalize(s):return " ".join(s.casefold().strip().split())
    return [{"id":q["id"],"correct":normalize(answers.get(q["id"],""))==normalize(q["answer"]),"answer":q["answer"],"excerpt":q["excerpt"],"document_id":q["document_id"],"title":q["title"],"page":q["page"]} for q in questions]
