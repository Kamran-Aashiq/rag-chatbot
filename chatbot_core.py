from langgraph.graph import StateGraph, START, END
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
llm = ChatOpenAI(model="gpt-5-mini", temperature=0.9)
LLM_AVAILABLE = llm is not None 
# Splitter and embeddings setup
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
try:
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    EMBEDDINGS_AVAILABLE = True
except Exception as e:
    embeddings = None
    EMBEDDINGS_AVAILABLE = False
    print("Warning: OpenAIEmbeddings initialization failed (embeddings unavailable):", e)

# Vectorstore persistence folder
VECTORSTORE_DIR = "vectorstore"

# Try to load an existing vectorstore from disk, otherwise initialize as None
def load_or_create_embeddings(docs_folder="literature", embeddings_model="text-embedding-3-small"):
    """Automatically load existing vectorstore or create from documents folder"""
    global vectorstore
    
    # Try to load existing vectorstore first
    if os.path.exists(VECTORSTORE_DIR) and EMBEDDINGS_AVAILABLE:
        try:
            allow_deser = os.environ.get('ALLOW_DANGEROUS_DESERIALIZATION', '0') in ('1', 'true', 'True')
            if allow_deser:
                vectorstore = FAISS.load_local(VECTORSTORE_DIR, embeddings, allow_dangerous_deserialization=True)
                print(f"✓ Loaded existing vectorstore from {VECTORSTORE_DIR}")
                return True
            else:
                vectorstore = FAISS.load_local(VECTORSTORE_DIR, embeddings)
                print(f"✓ Loaded existing vectorstore from {VECTORSTORE_DIR}")
                return True
        except Exception as e:
            print(f"✗ Failed to load vectorstore: {e}")
    
    # If no vectorstore exists, check for documents to index
    if os.path.exists(docs_folder) and EMBEDDINGS_AVAILABLE:
        print(f"📁 Found documents folder, checking for PDFs...")
        pdf_files = []
        for file in os.listdir(docs_folder):
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(docs_folder, file))
        
        if pdf_files:
            print(f"📄 Found {len(pdf_files)} PDFs to index...")
            try:
                from indexer import index_documents
                result = index_documents(pdf_files, save_metadata=False)
                if result.get('indexed', 0) > 0:
                    print(f"✓ Successfully indexed {result['indexed']} documents")
                    # Load the newly created vectorstore
                    vectorstore = FAISS.load_local(VECTORSTORE_DIR, embeddings, allow_dangerous_deserialization=True)
                    return True
            except Exception as e:
                print(f"✗ Failed to index documents: {e}")
    
    print("ℹ️ No vectorstore available - chatbot will use general knowledge only")
    return False

# Define docs_folder AFTER the function
docs_folder = "literature"

# Call the function
load_or_create_embeddings()
# Prompt template
prompt_template = PromptTemplate(
    input_variables=["context", "question"],
    template="""
You are **AquaAI**, an AI assistant specialized in water management, climate change,
and sustainability. You help students, researchers, policymakers, and communities
understand problems and find solutions.

📄 Context from documents:
{context}

❓ User Question:
{question}

Rules:
- If the user greets reply politely and conversationally. Do NOT mention documents or context.
- If the user asks to **summarize, explain, or analyze the document**, always use the context below.
- If the user asks about water, climate, irrigation, or sustainability → use the context if relevant; otherwise, rely on your knowledge.
- If no useful context is available, answer from general knowledge but stay on topic.
- Keep answers clear, natural, and under 100 words unless the user asks for detail.
- If user asks about water and climate related, end with a practical tip, recommendation, or insight when possible.
"""
)

# Helper to format docs
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# LangGraph Nodes
def retrieve_node(state):
    query = state.get("question")
    global vectorstore
    state["docs"] = []
    state["use_context"] = False
    
    print(f"DEBUG: Vectorstore available: {vectorstore is not None}")
    print(f"DEBUG: Query: {query}")
    
    if not vectorstore:
        print("DEBUG: No vectorstore available - skipping retrieval")
        return state

    try:
        results = vectorstore.similarity_search_with_score(query, k=4)
        print(f"DEBUG: Found {len(results)} results")
        if results:
            docs, scores = zip(*results)
            state["docs"] = list(docs)
            state["scores"] = list(scores)
            state["use_context"] = True
    except Exception as e:
        print(f"DEBUG: Retrieval error: {e}")
        state["docs"] = []
        state["use_context"] = False
    return state

def format_node(state):
    # Only set context if we have docs to include
    if state.get("use_context") and state.get("docs"):
        state["context"] = format_docs(state["docs"])
    else:
        state["context"] = ""
    return state


def prompt_node(state):
    # Expect calling code to provide conversation history in state['history']
    history = state.get('history', '')
    # If no context is available, give the LLM just the user question and history
    # Always use the instruction-driven prompt template so the LLM receives the rules.
    # If we have docs, include them in context; otherwise pass an empty context but keep the rules.
    question_text = f"{history}\nUser: {state['question']}"
    context_text = state.get("context") if state.get("use_context") and state.get("context") else ""
    state["prompt"] = prompt_template.format(context=context_text, question=question_text)
    return state


def llm_node(state):
    if llm is None:
        raise RuntimeError("LLM is not configured. Set OPENAI_API_KEY or configure the LLM before invoking the graph.")
    # Optional debug logging controlled by env var AQUAAI_DEBUG
    DEBUG = os.environ.get('AQUAAI_DEBUG', '0') == '1'
    if DEBUG:
        print('--- Prompt sent to LLM ---')
        print(state.get('prompt'))
        print('--- End prompt ---')

    # Invoke the LLM. Some langchain chat models support streaming APIs and some don't;
    # use a small helper that tries .predict, then falls back to .generate and extracts text.
    prompt_text = state["prompt"]

    def _call_llm(model, prompt_text):
        # Try the simplest synchronous API first
        try:
            return model.invoke(prompt_text).content
        except Exception:
            pass
        # Try the generate API (returns an LLMResult with generations)
        try:
            res = model.generate([prompt_text])
            # res.generations is a list of lists of Generation objects
            texts = []
            for gen_list in res.generations:
                if gen_list and hasattr(gen_list[0], 'text'):
                    texts.append(gen_list[0].text)
            return "\n\n".join(texts)
        except Exception as e:
            # As a last resort, try __call__
            try:
                return model(prompt_text)
            except Exception:
                raise RuntimeError(f"Failed to invoke LLM: {e}")

    state["raw_response"] = _call_llm(llm, prompt_text)

    if DEBUG:
        print('--- Raw response from LLM ---')
        print(state.get('raw_response'))
        print('--- End raw response ---')
    return state


def parse_node(state):
    parser = StrOutputParser()
    state["final_answer"] = parser.invoke(state["raw_response"])
    return state


# LangGraph Workflow
graph = StateGraph(dict)
graph.add_node("retrieve", retrieve_node)
graph.add_node("format", format_node)
graph.add_node("prompt", prompt_node)
graph.add_node("llm", llm_node)
graph.add_node("parse", parse_node)
graph.add_edge(START, "retrieve")
graph.add_edge("retrieve", "format")
graph.add_edge("format", "prompt")
graph.add_edge("prompt", "llm")
graph.add_edge("llm", "parse")
graph.add_edge("parse", END)
langgraph_app = graph.compile()

# Expose helper to reload or set vectorstore from external code if needed
def set_vectorstore(vs):
    global vectorstore
    vectorstore = vs


__all__ = ["langgraph_app", "VECTORSTORE_DIR", "embeddings", "splitter", "set_vectorstore", "llm", "LLM_AVAILABLE", "EMBEDDINGS_AVAILABLE"]
