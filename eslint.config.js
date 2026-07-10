// Flat config for ESLint 9+ (minimal, no extra deps beyond eslint)
export default [
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        // Browser + a few used in this project
        document: 'readonly',
        window: 'readonly',
        navigator: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        URL: 'readonly',
        location: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        YT: 'readonly', // may be referenced in old report data
      },
    },
    rules: {
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-console': 'off',
    },
  },
  {
    ignores: [
      'node_modules/**',
      'cards/**',
      'music/**',
      'playlists/**',
      'tools/__pycache__/**',
      '*.min.js',
      'eslint.config.js', // self
    ],
  },
];
