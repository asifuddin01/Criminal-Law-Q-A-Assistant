| Model | Stage | System | Measured | Retrieval recall | Citation precision | Answer hit rate | Excerpt validity | Refusal accuracy |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-oss-120b | 1 | baseline-llm-only | 93/95 | n/a | 18.4% | 25.7% | 0.0% | 85.0% |
| openai/gpt-oss-120b | 2 | rag-naive-chunks | 95/95 | 48.6% | 54.9% | 55.6% | 74.6% | 71.6% |
| qwen2.5:3b-instruct | 1 | baseline-llm-only | 100/101 | n/a | 6.9% | 1.3% | 0.0% | 73.0% |
| qwen2.5:3b-instruct | 2 | rag-naive-chunks | 101/101 | 45.5% | 36.4% | 33.8% | 49.4% | 81.2% |
| qwen2.5:3b-instruct | 3 | rag-legal-chunks | 100/101 | 82.9% | 79.0% | 75.0% | 52.6% | 85.0% |
| qwen2.5:3b-instruct | 4 | rag-full-corpus | 99/101 | 88.0% | 75.0% | 78.7% | 41.6% | 87.9% |
