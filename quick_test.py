# to check document retrieval from Qdrant
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
from app.rag.chain import get_retriever

retriever = get_retriever(k=4)
docs = retriever.invoke('What is tracing in Langfuse?')

for i, doc in enumerate(docs):
    print(f'--- Chunk {i+1} (source: {doc.metadata.get("source", "unknown")})')
    print(doc.page_content[:300])
    print()