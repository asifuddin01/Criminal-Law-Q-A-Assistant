| Model | Stage | System | Measured | Retrieval recall | Citation precision | Answer hit rate | Excerpt validity | Refusal accuracy |
|---|---|---|---|---|---|---|---|---|
| openai/gpt-oss-120b | 1 | baseline-llm-only | 93/95 | n/a | 18.4% | 25.7% | 0.0% | 85.0% |
| openai/gpt-oss-120b | 2 | rag-naive-chunks | 62/95 | 50.0% | 52.1% | 58.6% | 75.0% | 77.4% |
| qwen2.5:3b-instruct | 1 | baseline-llm-only | 93/95 | n/a | 7.4% | 1.4% | 0.0% | 71.0% |
| qwen2.5:3b-instruct | 2 | rag-naive-chunks | 94/95 | 48.6% | 36.8% | 36.1% | 49.4% | 83.0% |
| qwen2.5:3b-instruct | 3 | rag-legal-chunks | 93/95 | 88.6% | 80.8% | 80.0% | 53.2% | 86.0% |
