import tseslint from 'typescript-eslint'
import react from 'eslint-plugin-react'

export default tseslint.config(
  {
    // Global ignores
    ignores: [
      'dist/**',
      'node_modules/**',
      'electron/**',
      'src/lib/block-registry.generated.ts',
      'src/lib/block-configs.generated.ts',
      'src/lib/generated/**',
      'src/api/generated-types.ts',
    ],
  },
  // TypeScript rules for source files
  {
    files: ['src/**/*.ts', 'src/**/*.tsx'],
    plugins: {
      '@typescript-eslint': tseslint.plugin,
      react,
    },
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      // Phase 1: warn on explicit any — will escalate to error after cleanup
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
)
