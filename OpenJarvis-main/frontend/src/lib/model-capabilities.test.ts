import { describe, expect, it } from 'vitest';

import { isCloudModel, isEmbedOnlyModel } from './model-capabilities';

describe('isEmbedOnlyModel', () => {
  it.each([
    'nomic-embed-text',
    'mxbai-embed-large',
    'text-embedding-3-small',
    'all-minilm:latest',
    'hf.co/BAAI/bge-m3:latest',
  ])('classifies %s as embedding-only', (modelId) => {
    expect(isEmbedOnlyModel(modelId)).toBe(true);
  });

  it.each(['qwen3.5:4b', 'codegemma:7b'])('keeps %s available for chat', (modelId) => {
    expect(isEmbedOnlyModel(modelId)).toBe(false);
  });
});

describe('isCloudModel', () => {
  it.each([
    'openrouter/recursive/flint-v1.0:free',
    'gpt-4o-mini',
    'claude-sonnet-4-6',
    'gemini-2.5-flash',
    'atlascloud/openai/gpt-4.1-mini',
  ])('classifies %s as cloud', (modelId) => {
    expect(isCloudModel(modelId)).toBe(true);
  });

  it.each(['qwen3.5:4b', 'mlx-community/Qwen2.5:7B'])(
    'keeps %s local',
    (modelId) => {
      expect(isCloudModel(modelId)).toBe(false);
    },
  );
});
