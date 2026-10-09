// Task 10: new images cannot ship without alt (install with:
//   pnpm add -D eslint eslint-plugin-jsx-a11y
// then `pnpm lint`). Inert until the plugin is installed.
/** @type {import('eslint').Linter.Config[]} */
export default [
  {
    files: ["client/**/*.{ts,tsx}"],
    rules: {
      "jsx-a11y/alt-text": "error",
    },
  },
];
