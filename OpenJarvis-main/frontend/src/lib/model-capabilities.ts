const EMBEDDING_MODEL_PREFIXES = [
  'all-minilm',
  'bge-',
  'bge_',
  'e5-',
  'e5_',
  'gte-',
  'gte_',
  'jina-embeddings',
  'nomic-bert',
  'sentence-transformers',
];

const CLOUD_MODEL_PREFIXES = [
  'openrouter/',
  'gpt-',
  'chatgpt-',
  'o1',
  'o3',
  'o4',
  'claude-',
  'gemini-',
  'minimax-',
  'atlascloud/',
];

const LOCAL_HF_ORG_PREFIXES = [
  'mlx-community/',
  'bartowski/',
  'unsloth/',
  'lmstudio-community/',
];

export function isEmbedOnlyModel(modelId: string): boolean {
  const name = (modelId || '').trim().toLowerCase();
  const leaf = name.slice(name.lastIndexOf('/') + 1).split(':')[0];
  return (
    leaf.includes('embed') ||
    leaf.includes('minilm') ||
    EMBEDDING_MODEL_PREFIXES.some((prefix) => leaf.startsWith(prefix))
  );
}

/** Keep cloud selections when /v1/models reports only local models. */
export function isCloudModel(modelId: string): boolean {
  const name = (modelId || '').trim().toLowerCase();
  if (!name || LOCAL_HF_ORG_PREFIXES.some((prefix) => name.startsWith(prefix))) {
    return false;
  }
  return (
    CLOUD_MODEL_PREFIXES.some((prefix) => name.startsWith(prefix)) ||
    name.includes('/')
  );
}
