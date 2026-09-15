| Model | Stage | System | Measured | Retrieval recall | Citation precision | Answer hit rate | Excerpt validity | Refusal accuracy | Excerpt validity (as written) | Misattributed | Fabricated | Over-elided | Recomposed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-oss-120b | 1 | baseline-llm-only | 93/93 of 101 | n/a | 17.9% | 24.0% | 0.0% | 86.0% | 0.0% | 0.0% | 100.0% | 0.0% | 0.0% |
| openai/gpt-oss-120b | 2 | rag-naive-chunks | 95/95 of 101 | 45.5% | 54.9% | 51.9% | 96.2% | 66.3% | 76.1% | 0.8% | 2.3% | 0.8% | 0.0% |
| openai/gpt-oss-120b | 3 | rag-legal-chunks | 101/101 | 80.5% | 79.3% | 80.5% | 90.9% | 84.2% | 62.4% | 0.0% | 0.6% | 8.5% | 0.0% |
| openai/gpt-oss-120b | 4 | rag-full-corpus | 101/101 | 81.8% | 72.9% | 83.1% | 91.3% | 87.1% | 60.9% | 0.0% | 1.9% | 6.2% | 0.6% |
| qwen2.5:3b-instruct | 1 | baseline-llm-only | 101/101 | n/a | 6.9% | 1.3% | 0.0% | 73.3% | 0.0% | 0.0% | 100.0% | 0.0% | 0.0% |
| qwen2.5:3b-instruct | 2 | rag-naive-chunks | 101/101 | 63.6% | 61.2% | 48.0% | 52.9% | 90.1% | 42.9% | 18.6% | 28.6% | 0.0% | 0.0% |
| qwen2.5:3b-instruct | 3 | rag-legal-chunks | 101/101 | 80.5% | 66.3% | 63.6% | 83.9% | 88.1% | 67.7% | 5.4% | 10.8% | 0.0% | 0.0% |
| qwen2.5:3b-instruct | 4 | rag-full-corpus | 101/101 | 81.8% | 59.1% | 61.0% | 87.5% | 90.1% | 62.5% | 6.2% | 6.2% | 0.0% | 0.0% |
