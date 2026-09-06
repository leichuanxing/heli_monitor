import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import tseslint from '@vue/eslint-config-typescript'
export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  ...tseslint(),
  {
    ignores: ['dist/**'],
    rules: {
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-expressions': 'off',
    },
  },
]
