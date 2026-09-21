# Kev ROCm baseline — 2026-09-21

Kev 0.8B and 4B completed finite trials on an AMD Radeon 890M (`gfx1150`). All model parameters were asserted to be on the HIP GPU during GPU requests. No CPU fallback was allowed in that phase. Each process exited after its trial and released its allocation.

These measurements precede the MCP implementation. They establish a working ROCm inference path, not MCP compatibility or production readiness.

## Workload and results

Three synthetic inputs covered billing, shipping and account access. Each input asked three questions: a department choice, a double-charge yes/no decision and an urgency rating. Each request ran three times on GPU. All nine expected decisions passed for both models; score checks used a tolerance of 0.1.

| Case | 0.8B warm model time | 4B warm model time |
|---|---:|---:|
| Billing | 187.8 ms | 697.8 ms |
| Shipping | 193.3 ms | 680.25 ms |
| Account access | 148.0 ms | 581.3 ms |
| Peak PyTorch GPU allocation | 1.67 GiB | 8.32 GiB |

Each request contained 109–115 encoded input tokens. Warm times are medians of the second and third requests per case. Timings came from synchronized model execution through the FastAPI handler using TestClient; they exclude network transport. The first GPU request took 5,500.7 ms for 0.8B and 2,066.4 ms for 4B. Those first requests are not a controlled cold-start comparison because shared runtime/compiler caches may have been warm for the later trial.

CPU and GPU probabilities matched at rounded API precision. This is not exact tensor parity. These easy cases do not establish general accuracy, calibration, long-context performance, concurrent capacity or a quality advantage for 4B.

## Reproducibility record

- Python 3.12.13; PyTorch 2.8.0+rocm7.12.0; HIP 7.12.60610-2bd1678d3d.
- Triton 3.4.0+rocm7.12.0; Transformers 5.17.0; PEFT 0.21.0.
- LoRA merged in FP32 on CPU, then a BF16 backbone and FP32 pointer head moved to GPU.
- Reference PyTorch causal-convolution and Gated DeltaNet implementations. Flash Linear Attention and causal-conv1d were not installed. These results do not establish an optimized ROCm performance ceiling.
- HIP exposed 29,424 MiB of unified GPU memory.

| Artifact | Pinned revision |
|---|---|
| Kev source | `4f8110a3f8620cc3a182ae9a708e4398492c4b1a` |
| jaredpalmer/kev-0.8b | `225679690cdd1de6fceb1258b1bddf61c493cee9` |
| Qwen/Qwen3.5-0.8B-Base | `dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68` |
| jaredpalmer/kev-4b | `4bc64c6b4c4881148661ffb823ce21fcfdc79a0e` |
| Qwen/Qwen3.5-4B-Base | `1001bb4d826a52d1f399e183466143f4da7b741b` |

The source, dependency environment, model artifacts, scripts and raw results were retained in the private experiment workspace. This public report omits internal addresses and paths. A portable validation runner and fresh evidence are deliverables of IP-001; this report alone is not a complete reproduction kit.
