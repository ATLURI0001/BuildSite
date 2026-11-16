# Headless Blender Render Queue Architecture

## Overview
BuildSite turns verified Git commit history into evolving, photorealistic architectural villas using headless Blender instances.

## Render Worker Pipeline
1. **State Ingestion**: Fetch daily verified commit count and code velocity.
2. **Scene Mutation**: Parametric procedural modification of the villa geometry (foundations, framing, roofing, interior).
3. **Cycles / EEVEE Dispatch**: Execute headless frame rendering with OptiX / CUDA hardware acceleration.
4. **Compression**: Output optimized WebP/PNG artifacts for GitHub profile README embedding.
