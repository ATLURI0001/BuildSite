# Render Time Profiling & Fallback Guidelines

## Performance Budgets
- Target Render Time (GPU): < 8 seconds per frame
- Fallback Render Time (CPU 8-core): < 45 seconds per frame
- Maximum Peak VRAM: 4.0 GB

## Fallback Sequence
1. Attempt hardware OptiX / Vulkan rendering.
2. If driver allocation fails (CUDA_ERROR_OUT_OF_MEMORY), downgrade sample count by 50%.
3. Fall back to multi-threaded CPU rendering with ambient occlusion baking.
