"""Declarative node registration manifest for Studio NodeRegistry."""

NODE_PLUGIN_MANIFEST: list[dict[str, str]] = [
    {
        "node_type": "openai_generator",
        "module": "sage.middleware.operators.rag",
        "symbol": "OpenAIGenerator",
    },
    {
        "node_type": "hf_generator",
        "module": "sage.middleware.operators.rag",
        "symbol": "HFGenerator",
    },
    {
        "node_type": "chroma_retriever",
        "module": "sage.middleware.operators.rag",
        "symbol": "ChromaRetriever",
    },
    {
        "node_type": "bge_reranker",
        "module": "sage.middleware.operators.rag",
        "symbol": "BGEReranker",
    },
    {
        "node_type": "qa_promptor",
        "module": "sage.middleware.operators.rag",
        "symbol": "QAPromptor",
    },
    {
        "node_type": "character_splitter",
        "module": "sage.middleware.operators.rag.chunk",
        "symbol": "CharacterSplitter",
    },
    {
        "node_type": "memory_writer",
        "module": "sage.middleware.operators.rag",
        "symbol": "MemoryWriter",
    },
    {
        "node_type": "bocha_web_search",
        "module": "sage.middleware.operators.rag",
        "symbol": "BochaWebSearch",
    },
]
