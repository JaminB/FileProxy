const security = require('eslint-plugin-security');
const tsParser = require('@typescript-eslint/parser');

module.exports = [
  security.configs.recommended,
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tsParser,
    },
  },
];
