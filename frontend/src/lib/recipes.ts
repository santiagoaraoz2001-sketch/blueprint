import type { Node, Edge } from '@xyflow/react'
import type { BlockNodeData } from '@/stores/pipelineStore'

export interface Recipe {
    id: string
    name: string
    description: string
    tags: string[]
    nodes: Node<BlockNodeData>[]
    edges: Edge[]
    author?: string
    version?: string
    walkthrough?: string[]
    longDescription?: string
}

export const COMMUNITY_RECIPES: Recipe[] = [
    {
        id: 'recipe-rag-basic',
        name: 'Standard RAG Pipeline',
        description: 'A complete Retrieval-Augmented Generation pipeline including document ingestion, chunking, vector embedding, and a retrieval agent.',
        tags: ['rag', 'agents', 'local'],
        author: 'Blueprint Team',
        version: '1.2.0',
        longDescription: 'Build a production-ready Retrieval-Augmented Generation system from scratch. This recipe chains four blocks together to create an end-to-end pipeline: ingest documents from a local directory, split them into semantically meaningful chunks, embed those chunks into a vector store, and finally run a retrieval agent that answers user queries using the stored knowledge. Ideal for building internal knowledge bases, Q&A bots, and documentation assistants.',
        walkthrough: [
            'Document Ingestion reads all files from the specified directory using the glob pattern, extracting raw text content.',
            'Text Chunker splits the raw text into overlapping segments using a recursive strategy, preserving semantic boundaries.',
            'Vector Store Builder embeds each chunk using a local embedding model and indexes them into a ChromaDB collection.',
            'Retrieval Agent receives user queries, searches the vector store for relevant chunks, optionally re-ranks results, and generates a grounded response.'
        ],
        nodes: [
            {
                id: 'node_rag_1',
                type: 'blockNode',
                position: { x: 100, y: 100 },
                data: {
                    type: 'document_ingestion',
                    label: 'Document Ingestion',
                    category: 'external',
                    icon: 'FileText',
                    accent: '#F97316',
                    config: { directory_path: '', glob_pattern: '*.txt' },
                    status: 'idle',
                    progress: 0
                }
            },
            {
                id: 'node_rag_2',
                type: 'blockNode',
                position: { x: 400, y: 100 },
                data: {
                    type: 'text_chunker',
                    label: 'Text Chunker',
                    category: 'data',
                    icon: 'Scissors',
                    accent: '#22D3EE',
                    config: { chunk_size: 1000, chunk_overlap: 200, strategy: 'recursive' },
                    status: 'idle',
                    progress: 0
                }
            },
            {
                id: 'node_rag_3',
                type: 'blockNode',
                position: { x: 700, y: 50 },
                data: {
                    type: 'vector_store_build',
                    label: 'Vector Store Builder',
                    category: 'embedding',
                    icon: 'Database',
                    accent: '#FB7185',
                    config: { store_type: 'chroma', collection_name: 'blueprint_rag' },
                    status: 'idle',
                    progress: 0
                }
            },
            {
                id: 'node_rag_4',
                type: 'blockNode',
                position: { x: 1000, y: 150 },
                data: {
                    type: 'retrieval_agent',
                    label: 'Retrieval Agent (RAG)',
                    category: 'agents',
                    icon: 'Search',
                    accent: '#F43F5E',
                    config: { top_k: 5, rerank: true, max_tokens: 1024 },
                    status: 'idle',
                    progress: 0
                }
            }
        ],
        edges: [
            { id: 'edge_rag_1', source: 'node_rag_1', target: 'node_rag_2', sourceHandle: 'dataset', targetHandle: 'dataset', animated: true, style: { stroke: '#4ae38c', strokeWidth: 1.5 } },
            { id: 'edge_rag_2', source: 'node_rag_2', target: 'node_rag_3', sourceHandle: 'dataset', targetHandle: 'dataset', animated: true, style: { stroke: '#4ae38c', strokeWidth: 1.5 } },
            { id: 'edge_rag_3', source: 'node_rag_3', target: 'node_rag_4', sourceHandle: 'config', targetHandle: 'config', animated: true, style: { stroke: '#4ae38c', strokeWidth: 1.5 } }
        ]
    },
    {
        id: 'recipe-synthetic-data',
        name: 'Synthetic Data Generator',
        description: 'Automatically generate formatted dataset rows using a local LLM prompt for training or evaluation purposes.',
        tags: ['data generation', 'llm', 'synthetic'],
        author: 'Blueprint Team',
        version: '1.0.0',
        longDescription: 'Generate high-quality synthetic training data without manual annotation. This minimal two-block pipeline uses a local LLM to produce structured dataset rows based on configurable templates and prompts. The generated data is immediately available for preview and can be exported for fine-tuning or evaluation workflows. Adjust temperature and diversity penalty to control the variety and creativity of generated samples.',
        walkthrough: [
            'Synthetic Data Gen uses a local LLM to generate structured dataset rows based on your prompt template and configuration.',
            'Data Preview displays the generated rows in a tabular format so you can inspect quality before exporting.'
        ],
        nodes: [
            {
                id: 'node_synth_1',
                type: 'blockNode',
                position: { x: 200, y: 150 },
                data: {
                    type: 'synthetic_data_gen',
                    label: 'Synthetic Data Gen',
                    category: 'data',
                    icon: 'Sparkles',
                    accent: '#22D3EE',
                    config: { num_samples: 100, temperature: 0.8, diversity_penalty: 0.0 },
                    status: 'idle',
                    progress: 0
                }
            },
            {
                id: 'node_synth_2',
                type: 'blockNode',
                position: { x: 500, y: 150 },
                data: {
                    type: 'data_preview',
                    label: 'Data Preview',
                    category: 'data',
                    icon: 'Eye',
                    accent: '#22D3EE',
                    config: { num_rows: 20 },
                    status: 'idle',
                    progress: 0
                }
            }
        ],
        edges: [
            { id: 'edge_synth_1', source: 'node_synth_1', target: 'node_synth_2', sourceHandle: 'dataset', targetHandle: 'dataset', animated: true, style: { stroke: '#4ae38c', strokeWidth: 1.5 } }
        ]
    },
    {
        id: 'recipe-eval',
        name: 'Local Model Evaluation',
        description: 'Run multiple standardized benchmarks (LM Eval Harness & MMLU) on a local model simultaneously.',
        tags: ['evaluation', 'benchmarking', 'mmlu'],
        author: 'Community',
        version: '0.9.0',
        longDescription: 'Evaluate your local model against industry-standard benchmarks in parallel. This recipe sets up two independent evaluation blocks that can run simultaneously on the same model: LM Eval Harness for general reasoning tasks (HellaSwag, ARC) and MMLU for broad academic knowledge assessment. Compare results side-by-side to understand your model strengths and weaknesses across different capability dimensions.',
        walkthrough: [
            'LM Eval Harness runs the configured benchmark tasks (e.g., HellaSwag, ARC Easy) against your loaded model with automatic batching.',
            'MMLU Evaluation runs the Massive Multitask Language Understanding benchmark across all or selected academic subjects.',
            'Both evaluations run independently and can execute in parallel since they share no data dependencies.'
        ],
        nodes: [
            {
                id: 'node_eval_1',
                type: 'blockNode',
                position: { x: 200, y: 200 },
                data: {
                    type: 'lm_eval_harness',
                    label: 'LM Eval Harness',
                    category: 'metrics',
                    icon: 'ClipboardCheck',
                    accent: '#34D399',
                    config: { tasks: 'hellaswag,arc_easy', num_fewshot: 0, batch_size: 'auto' },
                    status: 'idle',
                    progress: 0
                }
            },
            {
                id: 'node_eval_2',
                type: 'blockNode',
                position: { x: 200, y: 400 },
                data: {
                    type: 'mmlu_eval',
                    label: 'MMLU Evaluation',
                    category: 'metrics',
                    icon: 'GraduationCap',
                    accent: '#34D399',
                    config: { subjects: 'all', num_fewshot: 5 },
                    status: 'idle',
                    progress: 0
                }
            }
        ],
        edges: []
    }
]
