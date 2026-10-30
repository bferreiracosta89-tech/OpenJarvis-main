import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ModelInfo } from '../types';

class MemoryStorage {
  private store = new Map<string, string>();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

const model = (id: string): ModelInfo => ({
  id,
  object: 'model',
  created: 0,
  owned_by: 'openjarvis',
});

beforeEach(() => {
  vi.resetModules();
  (globalThis as unknown as { localStorage: MemoryStorage }).localStorage =
    new MemoryStorage();
});

afterEach(() => {
  (globalThis as unknown as { localStorage?: MemoryStorage }).localStorage =
    undefined;
});

describe('setModels', () => {
  it('does not select an embedding-only model', async () => {
    const { useAppStore } = await import('./store');

    useAppStore.getState().setModels([model('nomic-embed-text')]);

    expect(useAppStore.getState().selectedModel).toBe('');
  });

  it('clears a missing selection when no chat fallback exists', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('deleted-chat-model');

    useAppStore.getState().setModels([model('nomic-embed-text')]);

    expect(useAppStore.getState().selectedModel).toBe('');
  });

  it('replaces an embedding selection with an available chat model', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('all-minilm:latest');

    useAppStore.getState().setModels([
      model('all-minilm:latest'),
      model('qwen3.5:4b'),
    ]);

    expect(useAppStore.getState().selectedModel).toBe('qwen3.5:4b');
  });

  it('preserves a selected cloud model when the server lists local models only', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('openrouter/recursive/flint-v1.0:free');

    useAppStore.getState().setModels([model('qwen3.5:4b')]);

    expect(useAppStore.getState().selectedModel).toBe(
      'openrouter/recursive/flint-v1.0:free',
    );
  });

  it('persists the selected model as the default setting', async () => {
    const { useAppStore } = await import('./store');

    useAppStore.getState().setSelectedModel('openrouter/google/gemma-4-31b-it:free');

    const raw = localStorage.getItem('openjarvis-settings');
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw as string).defaultModel).toBe(
      'openrouter/google/gemma-4-31b-it:free',
    );
  });

  it('restores a persisted cloud default when local models are loaded', async () => {
    localStorage.setItem(
      'openjarvis-settings',
      JSON.stringify({ defaultModel: 'openrouter/google/gemma-4-31b-it:free' }),
    );
    const { useAppStore } = await import('./store');

    useAppStore.getState().setModels([model('qwen3.5:4b')]);

    expect(useAppStore.getState().selectedModel).toBe(
      'openrouter/google/gemma-4-31b-it:free',
    );
  });

  it('uses the server cloud model as the initial chat model', async () => {
    const { useAppStore } = await import('./store');

    useAppStore.getState().setServerInfo({
      engine: 'multi',
      model: 'openrouter/recursive/flint-v1.0:free',
      agent: 'orchestrator',
    });

    expect(useAppStore.getState().selectedModel).toBe(
      'openrouter/recursive/flint-v1.0:free',
    );
  });
});
