import os
import argparse
import sqlite3
from datetime import datetime
from glob import glob
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

VECTORSTORE_DIR = "vectorstore"
DB_PATH = "chat_history.db"


def setup_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            filepath TEXT,
            uploaded_at TEXT
        )
    """)
    conn.commit()
    return conn


def index_documents(paths, embeddings_model="text-embedding-3-small", chunk_size=1000, chunk_overlap=200, save_metadata=True):
    """Index a list of PDF file paths into a FAISS vectorstore.

    - paths: iterable of file paths
    - saves/creates vectorstore in VECTORSTORE_DIR
    - optionally saves metadata into SQLite DB
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    try:
        embeddings = OpenAIEmbeddings(model=embeddings_model)
    except Exception as e:
        # Bubble up a clearer message for callers
        raise RuntimeError(f"Failed to initialize embeddings: {e}. Set OPENAI_API_KEY to enable embeddings.")

    # load existing vectorstore if present
# load existing vectorstore if present
    vectorstore = None
    if os.path.exists(VECTORSTORE_DIR):
        try:
            allow_deser = os.environ.get('ALLOW_DANGEROUS_DESERIALIZATION', '0') in ('1', 'true', 'True')
            if allow_deser:
                vectorstore = FAISS.load_local(VECTORSTORE_DIR, embeddings, allow_dangerous_deserialization=True)
            else:
                vectorstore = FAISS.load_local(VECTORSTORE_DIR, embeddings)
            print(f"Loaded existing vectorstore from {VECTORSTORE_DIR}")
        except Exception as e:
            print(f"Warning: failed loading existing vectorstore: {e}. A new one will be created.")
            vectorstore = None


    conn = None
    if save_metadata:
        conn = setup_db()

    indexed = 0
    for p in paths:
        if not os.path.isfile(p):
            print(f"Skipping {p}: not a file")
            continue
        if not p.lower().endswith('.pdf'):
            print(f"Skipping {p}: not a PDF")
            continue

        try:
            print(f"Indexing {p}...")
            try:
                loader = PyPDFLoader(p)
                docs = loader.load()
            except Exception as e:
                # Provide a clearer instruction when PDF parsing dependency missing
                raise RuntimeError(f"Failed to load PDF '{p}': {e}. Ensure 'pypdf' (or the required PDF backend) is installed: pip install pypdf")
            chunks = splitter.split_documents(docs)

            if vectorstore is None:
                vectorstore = FAISS.from_documents(chunks, embeddings)
            else:
                vectorstore.add_documents(chunks)

            # persist vectorstore after each file (keeps it safe)
            os.makedirs(VECTORSTORE_DIR, exist_ok=True)
            vectorstore.save_local(VECTORSTORE_DIR)

            if save_metadata and conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO documents (filename, filepath, uploaded_at) VALUES (?, ?, ?)",
                               (os.path.basename(p), os.path.abspath(p), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()

            indexed += 1
        except Exception as e:
            print(f"Failed to index {p}: {e}")

    if conn:
        conn.close()
    if indexed == 0:
        msg = "No documents were indexed."
        print(msg)
        return {"indexed": 0, "vectorstore_dir": None, "message": msg}
    else:
        msg = f"Indexed {indexed} document(s). Vectorstore saved at '{VECTORSTORE_DIR}'."
        print(msg)
        return {"indexed": indexed, "vectorstore_dir": VECTORSTORE_DIR, "message": msg}


def gather_files_from_folder(folder):
    p = os.path.abspath(folder)
    patterns = [os.path.join(p, "*.pdf")]
    files = []
    for pat in patterns:
        files.extend(glob(pat))
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description="Index PDFs into a FAISS vectorstore")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--files', nargs='+', help='One or more PDF file paths to index')
    group.add_argument('--folder', help='A folder; all PDF files inside will be indexed')
    parser.add_argument('--no-metadata', dest='save_metadata', action='store_false', help='Do not save metadata into SQLite DB')
    args = parser.parse_args()

    if args.folder:
        files = gather_files_from_folder(args.folder)
    else:
        files = args.files

    if not files:
        print('No PDF files found to index.')
        return

    index_documents(files, save_metadata=args.save_metadata)


if __name__ == '__main__':
    main()
