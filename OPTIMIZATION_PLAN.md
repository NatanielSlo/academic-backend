# Plan optymalizacji systemu RAG

## Zdiagnozowane problemy:

1. **Za restrykcyjny prompt** - LLM odmawia odpowiedzi nawet przy częściowo relevantnym kontekście
2. **Niski similarity threshold (0.3)** - przepuszcza słabo dopasowane chunki (noise)
3. **Małe top_k (5)** - za mało chunków dla złożonych pytań
4. **Brak re-rankingu** - prosty vector search bez dodatkowej walidacji
5. **Brak diagnostyki** - nie widzimy co faktycznie dostaje LLM

## Propozycje rozwiązań (priorytet):

### 🔥 PRIORYTET 1: Diagnostyka (szybkie)
**Co:** Dodaj logowanie zwracanych chunków + ich similarity scores
**Dlaczego:** Najpierw musimy zobaczyć CO faktycznie dostaje LLM
**Jak:** Rozszerz logowanie w rag.py aby zapisywać retrieved chunks

```python
# W rag.py po retrieve_chunks:
logger.info(f"Retrieved chunks similarities: {[c['similarity'] for c in chunks]}")
for i, chunk in enumerate(chunks):
    logger.debug(f"Chunk {i}: sim={chunk['similarity']:.3f}, text={chunk['text'][:100]}...")
```

### 🔥 PRIORYTET 2: Zwiększ threshold (łatwe)
**Co:** Podnieś `similarity_threshold` z 0.3 → 0.5 lub 0.6
**Dlaczego:** 0.3 to bardzo słaba korelacja - filtruj lepiej
**Jak:** Zmień w config.yaml
**Test:** Sprawdź ile chunków przechodzi przy różnych pytaniach

### 🔥 PRIORYTET 3: Zwiększ top_k + zrób re-ranking (średnie)
**Co:** 
- Zwiększ top_k do 15-20 
- Dodaj drugą fazę: LLM ocenia relevancję każdego chunka (0-10)
- Weź TOP 5 po re-rankingu

**Dlaczego:** Vector search jest niedokładny - drugi etap filtruje lepiej
**Jak:**
```python
def _rerank_chunks(self, question: str, chunks: List[Dict]) -> List[Dict]:
    """Re-rank chunks using LLM relevance scoring."""
    scored_chunks = []
    for chunk in chunks:
        prompt = f"""Rate relevance (0-10) of this text for question:
Question: {question}
Text: {chunk['text'][:300]}
Output only number:"""
        score = int(self.llm_service.complete(prompt, max_tokens=5))
        chunk['relevance_score'] = score
        scored_chunks.append(chunk)
    
    # Sort by relevance, take top 5
    return sorted(scored_chunks, key=lambda x: x['relevance_score'], reverse=True)[:5]
```

### 🟡 PRIORYTET 4: Złagodź prompt (łatwe)
**Co:** Pozwól LLM na częściowe odpowiedzi
**Jak:** Zmień w rag_qa.txt:
```
Jeśli masz częściową informację - podaj ją wyraźnie zaznaczając co jest pewne a czego nie ma w materiale.

Przykład: "Na podstawie dostępnych materiałów: [to co wiesz]. Jednak szczegółów dotyczących X nie ma w przeszukanych fragmentach."
```

### 🟡 PRIORYTET 5: Hybrid search (trudne)
**Co:** Połącz vector search + keyword search (BM25)
**Dlaczego:** Vector search może przegapić exact matches nazw/terminów
**Jak:** 
- Dodaj PostgreSQL full-text search
- Połącz wyniki: 70% vector + 30% keyword
- Lub użyj obu jako pre-filtering

### 🟡 PRIORYTET 6: Query expansion (średnie)
**Co:** Przed embeddingiem rozwiń pytanie o synonimy/kontekst
**Jak:**
```python
expanded_query = llm.complete(f"""Expand this query with synonyms/related terms:
Original: {question}
Expanded (keep it short):""")
```

### 🟡 PRIORYTET 7: Chunking improvements (trudne)
**Co:** Sprawdź jakość chunków
- Czy są czytelne?
- Czy mają wystarczający kontekst?
- Może overlapping chunks (sliding window)?

## Plan działania:

### Krok 1: DIAGNOSTYKA (30 min)
1. Dodaj szczegółowe logowanie
2. Wykonaj 5-10 testowych pytań
3. Zobacz co faktycznie wraca z bazy
4. Sprawdź similarity scores

### Krok 2: QUICK WINS (1h)
1. Zwiększ threshold do 0.5
2. Zwiększ top_k do 10
3. Złagodź prompt
4. Przetestuj ponownie

### Krok 3: RE-RANKING (2h)
1. Implementuj _rerank_chunks()
2. Dodaj relevance scoring
3. Przetestuj różne strategie

### Krok 4: ADVANCED (jeśli potrzeba)
1. Hybrid search
2. Query expansion
3. Better chunking

## Metryki do śledzenia:

- **Retrieval quality:** Ile chunków przechodzi threshold?
- **Relevance:** Czy chunki faktycznie odpowiadają na pytanie? (manual check)
- **Answer quality:** Czy LLM odpowiada czy mówi "nie wiem"?
- **Coverage:** % pytań z odpowiedzią vs "nie wiem"

## Szybki test diagnostyczny:

Uruchom to w test_rag.py:
```python
from app.services.rag import RAGService
import logging

logging.basicConfig(level=logging.DEBUG)

rag = RAGService()

# Test questions
questions = [
    "Was ist dynamic programming?",
    "Wie funktioniert Fibonacci Sequenz?",
    "Was ist Rekursion?",
]

for q in questions:
    print(f"\n{'='*70}")
    print(f"Q: {q}")
    print('='*70)
    
    # Get embedding
    emb = rag.embedding_service.embed_text(q)
    
    # Get chunks (before filtering)
    chunks = rag.db.search_similar_chunks(emb, top_k=10)
    
    print(f"\nRetrieved {len(chunks)} chunks:")
    for i, c in enumerate(chunks):
        print(f"  {i+1}. sim={c['similarity']:.3f} | {c['course_name']} L{c['lecture_number']}")
        print(f"     {c['text'][:100]}...")
    
    # Filter by threshold
    filtered = [c for c in chunks if c['similarity'] >= rag.similarity_threshold]
    print(f"\nAfter threshold filter ({rag.similarity_threshold}): {len(filtered)} chunks")
    
    # Generate answer
    result = rag.answer_question(q)
    print(f"\nAnswer:\n{result['answer']}")
```
